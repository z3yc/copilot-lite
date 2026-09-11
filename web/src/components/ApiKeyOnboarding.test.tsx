/**
 * ApiKeyOnboarding 测试：未配置 Key 时弹窗引导、已配置时不打扰、点击去配置回调。
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api";
import type { LLMSettings } from "../types";
import ApiKeyOnboarding from "./ApiKeyOnboarding";

vi.mock("../api", () => ({
  fetchLlmSettings: vi.fn(),
}));

const mocked = vi.mocked(api);

const base: LLMSettings = {
  base_url: "https://api.deepseek.com",
  model: "deepseek-chat",
  temperature: 0.7,
  max_tokens: 2048,
  api_key_set: false,
  api_key_preview: "",
  source: "none",
};

describe("ApiKeyOnboarding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("未配置 API Key 时弹窗提醒", async () => {
    mocked.fetchLlmSettings.mockResolvedValue({ ...base });
    render(<ApiKeyOnboarding onConfigure={vi.fn()} />);
    expect(await screen.findByText("先配置模型 API Key")).toBeInTheDocument();
  });

  it("已配置 API Key 时不弹窗", async () => {
    mocked.fetchLlmSettings.mockResolvedValue({
      ...base,
      api_key_set: true,
      api_key_preview: "sk-****test",
      source: "user",
    });
    render(<ApiKeyOnboarding onConfigure={vi.fn()} />);
    await waitFor(() => expect(mocked.fetchLlmSettings).toHaveBeenCalled());
    expect(screen.queryByText("先配置模型 API Key")).not.toBeInTheDocument();
  });

  it("点击「去配置」关闭弹窗并回调", async () => {
    mocked.fetchLlmSettings.mockResolvedValue({ ...base });
    const onConfigure = vi.fn();
    render(<ApiKeyOnboarding onConfigure={onConfigure} />);

    await userEvent.click(await screen.findByRole("button", { name: /去配置/ }));
    expect(onConfigure).toHaveBeenCalledTimes(1);
  });

  it("配置读取失败时不弹窗（不阻塞进入聊天）", async () => {
    mocked.fetchLlmSettings.mockRejectedValue(new Error("boom"));
    render(<ApiKeyOnboarding onConfigure={vi.fn()} />);
    await waitFor(() => expect(mocked.fetchLlmSettings).toHaveBeenCalled());
    expect(screen.queryByText("先配置模型 API Key")).not.toBeInTheDocument();
  });
});
