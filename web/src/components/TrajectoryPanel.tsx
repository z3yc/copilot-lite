/**
 * 回答轨迹面板：让「多智能体不是黑盒」——展开可见 路由 → 节点 → 工具 → 耗时。
 *
 * 轨迹内容（工具参数/结果）来自模型与外部数据，一律用 React 默认转义渲染，
 * 禁止 dangerouslySetInnerHTML（AGENTS §5）。
 */

import { Collapse, Tag, Typography } from "antd";

import type { Trajectory, TrajectoryStep } from "../types";

const { Text } = Typography;

const ENGINE_LABEL: Record<string, string> = {
  langgraph: "LangGraph",
  handwritten: "手写 ReAct",
};

function msTag(ms?: number) {
  if (typeof ms !== "number") return null;
  return (
    <Text type="secondary" style={{ fontSize: 12 }}>
      {" "}
      {ms}ms
    </Text>
  );
}

function StepDetail({ step }: { step: TrajectoryStep }) {
  if (step.type === "route") {
    return (
      <>
        <Tag color="blue">路由</Tag>
        <Text code>{step.route}</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {" "}
          （{step.source === "llm" ? "模型判定" : "关键词兜底"}）
        </Text>
        {msTag(step.ms)}
      </>
    );
  }
  if (step.type === "node") {
    return (
      <>
        <Tag color="purple">节点</Tag>
        <Text code>{step.node}</Text>
      </>
    );
  }
  if (step.type === "tool") {
    const pending = step.status === "pending_confirmation";
    return (
      <>
        <Tag color={pending ? "orange" : "green"}>工具</Tag>
        <Text code>{step.name}</Text>
        {pending && (
          <Text type="warning" style={{ fontSize: 12 }}>
            {" "}
            （待确认，尚未执行）
          </Text>
        )}
        {msTag(step.ms)}
        <div className="dim" style={{ fontSize: 12, wordBreak: "break-all" }}>
          参数：{step.arguments || "{}"}
        </div>
        {step.result && (
          <div className="dim" style={{ fontSize: 12, wordBreak: "break-all" }}>
            结果：{step.result}
          </div>
        )}
      </>
    );
  }
  return (
    <>
      <Tag>回复</Tag>
      <Text type="secondary" style={{ fontSize: 12 }}>
        {step.chars ?? 0} 字
      </Text>
    </>
  );
}

export default function TrajectoryPanel({ trajectory }: { trajectory?: Trajectory }) {
  if (!trajectory || !trajectory.steps?.length) return null;
  const summary = `${ENGINE_LABEL[trajectory.engine] ?? trajectory.engine} · ${
    trajectory.steps.length
  } 步 · ${trajectory.total_ms}ms${trajectory.truncated ? " · 已截断" : ""}`;
  return (
    <Collapse
      size="small"
      className="trajectory-panel"
      items={[
        {
          key: "trajectory",
          label: (
            <span>
              本次回答轨迹
              <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                {summary}
              </Text>
            </span>
          ),
          children: (
            <ol className="trajectory-steps" style={{ margin: 0, paddingLeft: 18 }}>
              {trajectory.steps.map((step, i) => (
                <li key={i} style={{ marginBottom: 6 }}>
                  <StepDetail step={step} />
                </li>
              ))}
            </ol>
          ),
        },
      ]}
    />
  );
}
