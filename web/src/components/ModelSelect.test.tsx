/**
 * ModelSelect 测试：未配置引导、可用模型加载与切换持久化、上游 /models 失败回退。
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import type { LLMSettings } from "../types";
import ModelSelect from "./ModelSelect";

vi.mock("../api", () => ({
  fetchLlmSettings: vi.fn(),
  fetchLlmModels: vi.fn(),
  saveLlmSettings: vi.fn(),
}));

const mocked = vi.mocked(api);

const userSettings: LLMSettings = {
  base_url: "https://api.example.com",
  model: "deepseek-chat",
  temperature: 0.5,
  max_tokens: 1024,
  api_key_set: true,
  api_key_preview: "sk-****test",
  source: "user",
};

describe("ModelSelect", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("未配置 Key 时展示引导按钮并回调", async () => {
    mocked.fetchLlmSettings.mockResolvedValue({
      ...userSettings,
      api_key_set: false,
      api_key_preview: "",
      source: "none",
    });
    const onOpenSettings = vi.fn();
    render(<ModelSelect onOpenSettings={onOpenSettings} />);

    const btn = await screen.findByRole("button", { name: /未配置模型/ });
    await userEvent.click(btn);
    expect(onOpenSettings).toHaveBeenCalledTimes(1);
    expect(mocked.fetchLlmModels).not.toHaveBeenCalled();
  });

  it("已配置 Key 时按配置加载可用模型", async () => {
    mocked.fetchLlmSettings.mockResolvedValue(userSettings);
    mocked.fetchLlmModels.mockResolvedValue({
      models: ["deepseek-chat", "deepseek-reasoner"],
      current: "deepseek-chat",
      source: "user",
    });
    render(<ModelSelect />);

    await screen.findByRole("combobox", { name: "选择模型" });
    await waitFor(() => expect(screen.getByText("deepseek-chat")).toBeInTheDocument());
    expect(mocked.fetchLlmModels).toHaveBeenCalledTimes(1);
  });

  it("切换模型时保留已存 Key 并持久化新模型", async () => {
    mocked.fetchLlmSettings.mockResolvedValue(userSettings);
    mocked.fetchLlmModels.mockResolvedValue({
      models: ["deepseek-chat", "deepseek-reasoner"],
      current: "deepseek-chat",
      source: "user",
    });
    mocked.saveLlmSettings.mockResolvedValue({
      ...userSettings,
      model: "deepseek-reasoner",
    });
    render(<ModelSelect />);

    await userEvent.click(await screen.findByRole("combobox", { name: "选择模型" }));
    await userEvent.click(await screen.findByTitle("deepseek-reasoner"));

    await waitFor(() =>
      expect(mocked.saveLlmSettings).toHaveBeenCalledWith({
        base_url: "https://api.example.com",
        model: "deepseek-reasoner",
        temperature: 0.5,
        max_tokens: 1024,
      })
    );
  });

  it("上游 /models 失败时回退为当前模型可选", async () => {
    mocked.fetchLlmSettings.mockResolvedValue(userSettings);
    mocked.fetchLlmModels.mockRejectedValue(new Error("502"));
    render(<ModelSelect />);

    await screen.findByRole("combobox", { name: "选择模型" });
    await waitFor(() => expect(screen.getByText("deepseek-chat")).toBeInTheDocument());
  });

  it("使用环境变量默认时模型只读", async () => {
    mocked.fetchLlmSettings.mockResolvedValue({ ...userSettings, source: "env" });
    mocked.fetchLlmModels.mockResolvedValue({
      models: ["deepseek-chat"],
      current: "deepseek-chat",
      source: "env",
    });
    render(<ModelSelect />);

    const combo = await screen.findByRole("combobox", { name: "选择模型" });
    await waitFor(() => expect(combo).toBeDisabled());
  });
});
