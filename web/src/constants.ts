import type { CSSProperties, ComponentType } from "react";
import {
  AppstoreOutlined,
  BookOutlined,
  CodeOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  FileWordOutlined,
  GlobalOutlined,
} from "@ant-design/icons";

/** 支持上传的文档扩展名（前端 accept 提示；后端仍会二次校验）。 */
export const ACCEPT_EXTENSIONS =
  ".md,.txt,.pdf,.docx,.py,.js,.ts,.tsx,.jsx,.java,.go,.rs,.c,.cpp,.sql,.html,.htm";

export interface SourceMeta {
  label: string;
  Icon: ComponentType<{ className?: string; style?: CSSProperties }>;
}

/** 知识来源类型 → 展示元信息（Ant 图标 + 中文名），KbPanel / DocCategoryNav 共用。 */
export const SOURCE_META: Record<string, SourceMeta> = {
  md: { label: "笔记", Icon: FileTextOutlined },
  wiki: { label: "Wiki", Icon: BookOutlined },
  pdf: { label: "PDF", Icon: FilePdfOutlined },
  docx: { label: "Word", Icon: FileWordOutlined },
  code: { label: "代码", Icon: CodeOutlined },
  web: { label: "网页", Icon: GlobalOutlined },
};

/** 分类导航"全部"项。 */
export const ALL_SOURCE_META: SourceMeta = { label: "全部", Icon: AppstoreOutlined };

/** 未知来源类型的兜底元信息。 */
export const DEFAULT_SOURCE_META: SourceMeta = { label: "其他", Icon: FileTextOutlined };

/** 取来源元信息（未知类型回退兜底）。 */
export function sourceMeta(type: string): SourceMeta {
  return SOURCE_META[type] ?? DEFAULT_SOURCE_META;
}
