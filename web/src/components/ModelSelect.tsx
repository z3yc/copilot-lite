import { useEffect, useState } from "react";
import { Button, Select, Tooltip, message } from "antd";
import { fetchLlmModels, fetchLlmSettings, saveLlmSettings } from "../api";
import type { LLMSettings } from "../types";

interface Props {
  /** 未配置 Key 时点击引导前往「个人主页 → 模型设置」 */
  onOpenSettings?: () => void;
}

/**
 * 聊天窗口的模型选择器。
 *
 * - 已配置个人 Key：按 Base URL + Key 拉取可用模型，切换后持久化到用户配置；
 * - 未配置 Key：显示「未配置模型」引导去配置；
 * - 使用环境变量默认（管理员配置）：模型只读，避免写入无 Key 的用户配置而失效。
 */
export default function ModelSelect({ onOpenSettings }: Props) {
  const [llm, setLlm] = useState<LLMSettings | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await fetchLlmSettings();
        if (cancelled) return;
        setLlm(s);
        if (!s.api_key_set) {
          setModels([]);
          return;
        }
        try {
          const res = await fetchLlmModels();
          if (cancelled) return;
          const list = res.models ?? [];
          // 确保当前模型始终在候选里（上游可能未返回）
          setModels(list.includes(s.model) ? list : [s.model, ...list]);
        } catch {
          // 上游不支持 /models 或网络失败：至少保留当前模型可选
          if (!cancelled) setModels([s.model]);
        }
      } catch (err) {
        console.error("加载模型配置失败", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const changeModel = async (model: string) => {
    if (!llm || model === llm.model) return;
    setSaving(true);
    try {
      // 不带 api_key：保留已存 Key，仅更新模型
      const saved = await saveLlmSettings({
        base_url: llm.base_url,
        model,
        temperature: llm.temperature,
        max_tokens: llm.max_tokens,
      });
      setLlm(saved);
      message.success(`已切换到 ${model}`);
    } catch (err) {
      message.error(`切换模型失败：${err}`);
    } finally {
      setSaving(false);
    }
  };

  // 初始加载：占位，避免闪一帧「未配置」
  if (!llm) {
    return (
      <Select
        size="small"
        loading
        disabled
        placeholder="模型"
        style={{ minWidth: 150 }}
        aria-label="选择模型"
      />
    );
  }

  if (!llm.api_key_set) {
    return (
      <Tooltip title="尚未配置 API Key，点击前往配置">
        <Button size="small" type="link" onClick={onOpenSettings}>
          未配置模型
        </Button>
      </Tooltip>
    );
  }

  const envControlled = llm.source === "env";
  const select = (
    <Select
      size="small"
      aria-label="选择模型"
      value={llm.model}
      loading={loading || saving}
      disabled={envControlled || saving}
      onChange={changeModel}
      options={models.map((m) => ({ value: m, label: m }))}
      style={{ minWidth: 150 }}
      notFoundContent={loading ? "加载中…" : "无可用模型"}
    />
  );

  return envControlled ? (
    <Tooltip title="当前使用环境变量默认模型（由管理员配置）">{select}</Tooltip>
  ) : (
    select
  );
}
