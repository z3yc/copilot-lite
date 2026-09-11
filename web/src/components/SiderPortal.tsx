import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { useSiderNav } from "../contexts/SiderNav";

/**
 * 把导航内容渲染进「工作区」侧栏的挂载点。
 *
 * - App 内（enabled）：portal 到侧栏；挂载点尚未就绪时先不渲染（避免闪动）。
 * - 无 Provider（单测/独立使用）：行内渲染 children，保持组件可测试。
 */
export default function SiderPortal({ children }: { children: ReactNode }) {
  const { el, enabled } = useSiderNav();
  if (!enabled) return <>{children}</>;
  if (!el) return null;
  return createPortal(children, el);
}
