import { createContext, useContext } from "react";

export interface SiderNavContextValue {
  /** 侧栏导航挂载点（App 内提供）。 */
  el: HTMLElement | null;
  /**
   * 是否处于「导航已迁移到侧栏」模式：
   * App 内为 true；单测/独立使用（无 Provider）为 false → 导航行内渲染，保证可测试与可复用。
   */
  enabled: boolean;
}

export const SiderNavContext = createContext<SiderNavContextValue>({
  el: null,
  enabled: false,
});

export const useSiderNav = () => useContext(SiderNavContext);
