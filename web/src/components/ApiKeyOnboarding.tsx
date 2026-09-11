import { useEffect, useState } from "react";
import { Button, Modal, Typography } from "antd";
import { KeyOutlined, SettingOutlined } from "@ant-design/icons";
import { fetchLlmSettings } from "../api";

const { Paragraph, Text } = Typography;

interface Props {
  /** 点击「去配置」：跳转到「个人主页 → 模型设置」 */
  onConfigure: () => void;
}

/**
 * 首次登录（或未配置 API Key 时）的第一件事：弹窗引导配置模型 Key。
 *
 * 部署默认不内置 Key，用户需在「个人主页 → 模型设置」填写 Base URL / Key / 模型
 * 后才能对话。读取配置失败时静默跳过，不阻塞进入聊天。
 */
export default function ApiKeyOnboarding({ onConfigure }: Props) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchLlmSettings()
      .then((s) => {
        if (!cancelled && !s.api_key_set) setOpen(true);
      })
      .catch((err) => {
        // 读取失败不打扰用户（不阻塞进入聊天）
        console.error("加载模型配置失败", err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Modal
      open={open}
      centered
      title="先配置模型 API Key"
      onCancel={() => setOpen(false)}
      footer={[
        <Button key="later" onClick={() => setOpen(false)}>
          稍后再说
        </Button>,
        <Button
          key="go"
          type="primary"
          icon={<SettingOutlined />}
          onClick={() => {
            setOpen(false);
            onConfigure();
          }}
        >
          去配置
        </Button>,
      ]}
    >
      <Paragraph>
        当前部署未内置模型 Key，需要你填写自己的 API Key 与模型信息后才能对话。
      </Paragraph>
      <Paragraph type="secondary" style={{ marginBottom: 0 }}>
        <KeyOutlined /> 打开<Text strong>个人主页 → 模型设置</Text>
        ，填入 Base URL、API Key 与模型名称，保存后即可开始对话。
      </Paragraph>
    </Modal>
  );
}
