/**
 * WikiPanel 组件测试：空间加载、页面列表、详情+反向链接、同步、新建空间。
 * 全部 mock api，不触网。
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import WikiPanel from "./WikiPanel";

vi.mock("../api", () => ({
  fetchWikiSpaces: vi.fn(),
  createWikiSpace: vi.fn(),
  deleteWikiSpace: vi.fn(),
  syncWikiSpace: vi.fn(),
  importWikiZip: vi.fn(),
  importWikiFiles: vi.fn(),
  resolveWikiPage: vi.fn(),
  resyncWikiPage: vi.fn(),
  fetchWikiPages: vi.fn(),
  fetchWikiPage: vi.fn(),
}));

const mocked = vi.mocked(api);

const SPACES = [
  { id: "s1", name: "my-vault", source_type: "upload", page_count: 2, last_synced_at: null },
];
const PAGES = {
  items: [
    { id: "p1", space_id: "s1", rel_path: "A.md", title: "A", slug: "a" },
    { id: "p2", space_id: "s1", rel_path: "B.md", title: "B", slug: "b" },
  ],
  total: 2,
  page: 1,
  page_size: 20,
};

describe("WikiPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.fetchWikiSpaces.mockResolvedValue(SPACES);
    mocked.fetchWikiPages.mockResolvedValue(PAGES);
    mocked.fetchWikiPage.mockResolvedValue({
      ...PAGES.items[0],
      content: "# A\n\n正文内容",
      tags: ["tag1"],
      links: [{ target_slug: "b", target_page_id: "p2", alias: null, kind: "link" }],
      backlinks: [{ source_page_id: "p2", source_title: "B" }],
    });
  });

  it("加载空间与页面列表", async () => {
    render(<WikiPanel />);
    expect(await screen.findByText("my-vault（2 页）")).toBeInTheDocument();
    expect(await screen.findByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
  });

  it("点击页面展示正文与反向链接", async () => {
    render(<WikiPanel />);
    fireEvent.click(await screen.findByText("A"));
    expect(await screen.findByText("正文内容")).toBeInTheDocument();
    expect(await screen.findByText(/反向链接（1）/)).toBeInTheDocument();
    expect(mocked.fetchWikiPage).toHaveBeenCalledWith("p1");
  });

  it("点击同步调用同步接口", async () => {
    mocked.syncWikiSpace.mockResolvedValue({
      added: 1,
      updated: 0,
      moved: 0,
      deleted: 0,
      failed: 0,
      total: 1,
    });
    render(<WikiPanel />);
    await screen.findByText("my-vault（2 页）");
    fireEvent.click(screen.getByRole("button", { name: /同步/ }));
    await waitFor(() => expect(mocked.syncWikiSpace).toHaveBeenCalledWith("s1"));
  });

  it("新建空间调用创建接口", async () => {
    mocked.createWikiSpace.mockResolvedValue({
      id: "s2",
      name: "new-vault",
      source_type: "upload",
      page_count: 0,
      last_synced_at: null,
    });
    render(<WikiPanel />);
    await screen.findByText("my-vault（2 页）");
    fireEvent.click(screen.getByRole("button", { name: /新建/ }));
    fireEvent.change(screen.getByPlaceholderText(/空间名称/), {
      target: { value: "new-vault" },
    });
    fireEvent.click(screen.getByRole("button", { name: /OK|确\s*定/ }));
    await waitFor(() =>
      expect(mocked.createWikiSpace).toHaveBeenCalledWith("new-vault", "upload", undefined)
    );
  });

  it("选择文件时调用多文件导入接口", async () => {
    mocked.importWikiFiles.mockResolvedValue({
      added: 1,
      updated: 0,
      moved: 0,
      deleted: 0,
      failed: 0,
      total: 1,
      skipped: 0,
      imported_files: 1,
    });
    render(<WikiPanel />);
    await screen.findByText("my-vault（2 页）");

    const input = screen.getByTestId("wiki-file-input") as HTMLInputElement;
    const file = new File(["# A"], "A.md", { type: "text/markdown" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(mocked.importWikiFiles).toHaveBeenCalled());
  });

  it("详情页可重新索引", async () => {
    mocked.resyncWikiPage.mockResolvedValue({
      ...PAGES.items[0],
      content: "# A\n\n正文内容",
      tags: [],
      links: [],
      backlinks: [],
      document_status: "ready",
    });
    render(<WikiPanel />);
    fireEvent.click(await screen.findByText("A"));
    await screen.findByText("正文内容");
    fireEvent.click(screen.getByRole("button", { name: /重新索引/ }));
    await waitFor(() => expect(mocked.resyncWikiPage).toHaveBeenCalledWith("p1"));
  });

  it("选择本地文件夹时传本地路径并自动同步", async () => {
    mocked.createWikiSpace.mockResolvedValue({
      id: "s3",
      name: "local-vault",
      source_type: "local",
      page_count: 0,
      last_synced_at: null,
    });
    mocked.syncWikiSpace.mockResolvedValue({
      added: 2,
      updated: 0,
      moved: 0,
      deleted: 0,
      failed: 0,
      total: 2,
    });
    render(<WikiPanel />);
    await screen.findByText("my-vault（2 页）");
    fireEvent.click(screen.getByRole("button", { name: /新建/ }));
    fireEvent.change(screen.getByPlaceholderText(/空间名称/), {
      target: { value: "local-vault" },
    });
    fireEvent.click(screen.getByText("本地文件夹（自托管）"));
    fireEvent.change(screen.getByPlaceholderText(/绝对路径/), {
      target: { value: "C:/Users/you/MyVault" },
    });
    fireEvent.click(screen.getByRole("button", { name: /OK|确\s*定/ }));
    await waitFor(() =>
      expect(mocked.createWikiSpace).toHaveBeenCalledWith(
        "local-vault",
        "local",
        "C:/Users/you/MyVault"
      )
    );
    await waitFor(() => expect(mocked.syncWikiSpace).toHaveBeenCalledWith("s3"));
  });
});
