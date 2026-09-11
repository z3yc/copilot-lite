/** keyboardActivate：非原生可点击元素的 Enter/Space 键盘触发契约。 */

import type { KeyboardEvent } from "react";
import { describe, expect, it, vi } from "vitest";

import { keyboardActivate } from "./a11y";

function keyEvent(key: string): KeyboardEvent {
  return { key, preventDefault: vi.fn() } as unknown as KeyboardEvent;
}

describe("keyboardActivate", () => {
  it("Enter 与 Space 触发处理函数", () => {
    const handler = vi.fn();
    const onKeyDown = keyboardActivate(handler);
    onKeyDown(keyEvent("Enter"));
    onKeyDown(keyEvent(" "));
    expect(handler).toHaveBeenCalledTimes(2);
  });

  it("其他按键不触发", () => {
    const handler = vi.fn();
    keyboardActivate(handler)(keyEvent("a"));
    expect(handler).not.toHaveBeenCalled();
  });
});
