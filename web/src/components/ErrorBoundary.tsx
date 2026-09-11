import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button, Result } from "antd";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message?: string;
}

/**
 * 全局错误边界：捕获子树渲染异常，避免整页白屏。
 * 只负责渲染兜底 UI；异步/事件处理器异常仍需各处 try/catch（React 边界不捕获这些）。
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 生产可上报到监控平台；此处至少保留控制台堆栈便于排查
    console.error("UI 渲染异常:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Result
          status="error"
          title="页面出现异常"
          subTitle={this.state.message || "请刷新页面后重试"}
          extra={
            <Button type="primary" onClick={() => window.location.reload()}>
              刷新页面
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}
