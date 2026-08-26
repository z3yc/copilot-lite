/**
 * LoginPage 组件测试：表单渲染、校验、登录/注册提交（mock api 模块）。
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as api from "../api";
import LoginPage from "./LoginPage";

vi.mock("../api", () => ({
  login: vi.fn(),
  register: vi.fn(),
  setToken: vi.fn(),
}));

const mocked = vi.mocked(api);

function fillAndSubmit(username: string, password: string) {
  fireEvent.change(screen.getByPlaceholderText("用户名"), {
    target: { value: username },
  });
  fireEvent.change(screen.getByPlaceholderText("密码（至少 6 位）"), {
    target: { value: password },
  });
  fireEvent.click(screen.getByRole("button", { name: "登 录" }));
}

describe("LoginPage", () => {
  it("渲染登录表单（标题 / 输入框 / 按钮）", () => {
    render(<LoginPage onSuccess={vi.fn()} />);
    expect(screen.getByText("Copilot-Lite")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("用户名")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("密码（至少 6 位）")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登 录" })).toBeInTheDocument();
  });

  it("空表单提交触发校验错误，不调用 login", async () => {
    render(<LoginPage onSuccess={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "登 录" }));

    expect(await screen.findByText("请输入用户名")).toBeInTheDocument();
    expect(await screen.findByText("请输入密码")).toBeInTheDocument();
    expect(mocked.login).not.toHaveBeenCalled();
  });

  it("登录成功：login → setToken → onSuccess", async () => {
    mocked.login.mockResolvedValue({
      token: "tok1",
      user: { id: "1", username: "alice", role: "user" },
    } as api.AuthResp);
    const onSuccess = vi.fn();
    render(<LoginPage onSuccess={onSuccess} />);

    fillAndSubmit("alice", "secret1");

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(mocked.login).toHaveBeenCalledWith("alice", "secret1");
    expect(mocked.setToken).toHaveBeenCalledWith("tok1");
  });

  it("切换到注册模式提交时调用 register", async () => {
    mocked.register.mockResolvedValue({
      token: "tok2",
      user: { id: "2", username: "bob", role: "user" },
    } as api.AuthResp);
    const onSuccess = vi.fn();
    render(<LoginPage onSuccess={onSuccess} />);

    fireEvent.click(screen.getByText("注 册"));
    fireEvent.change(screen.getByPlaceholderText("用户名"), {
      target: { value: "bob" },
    });
    fireEvent.change(screen.getByPlaceholderText("密码（至少 6 位）"), {
      target: { value: "secret1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "注册并登录" }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(mocked.register).toHaveBeenCalledWith("bob", "secret1");
    expect(mocked.setToken).toHaveBeenCalledWith("tok2");
  });

  it("登录失败时展示错误提示（不触发 onSuccess）", async () => {
    mocked.login.mockRejectedValue(new Error("用户名或密码错误"));
    const onSuccess = vi.fn();
    render(<LoginPage onSuccess={onSuccess} />);

    fillAndSubmit("alice", "wrong-password");

    await waitFor(() => expect(mocked.login).toHaveBeenCalled());
    expect(onSuccess).not.toHaveBeenCalled();
    expect(await screen.findByText(/用户名或密码错误/)).toBeInTheDocument();
  });
});
