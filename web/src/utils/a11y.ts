import type { KeyboardEvent } from "react";

/**
 * 为非原生可点击元素补齐键盘触发（配合 `role="button"` + `tabIndex={0}`）。
 * Enter / Space 等价于点击——`div`、`List.Item` 等无法原生聚焦的元素必须使用。
 */
export function keyboardActivate(handler: () => void) {
  return (event: KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handler();
    }
  };
}
