/**
 * 主题常量——JS 侧的单一来源。
 *
 * Ant Design 需要具体色值来推导派生色（hover/active 等），无法直接消费 CSS 变量，
 * 因此这里保留字面量，并**必须与 `styles.css` 的 `--color-primary` 保持一致**。
 * 组件内联样式请优先使用 `var(--color-primary)`，不要在此之外新增裸 hex。
 */
export const BRAND_PRIMARY = "#4f6ef7";

/** 与 `styles.css` 圆角 scale 对应的 antd 全局圆角（中号）。 */
export const BRAND_RADIUS = 10;
