import { useState } from "react";
import { Button, Card, Form, Input, Tabs, Typography, message } from "antd";
import { LockOutlined, RobotOutlined, UserOutlined } from "@ant-design/icons";
import { login, register, setToken } from "../api";

const { Title, Text } = Typography;

interface Props {
  onSuccess: () => void;
}

export default function LoginPage({ onSuccess }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const submit = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const resp =
        mode === "login"
          ? await login(values.username, values.password)
          : await register(values.username, values.password);
      setToken(resp.token);
      message.success(mode === "login" ? "欢迎回来！" : "注册成功，已自动登录");
      onSuccess();
    } catch (err) {
      message.error(`${err}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrap">
      <Card className="login-card">
        <div style={{ textAlign: "center", marginBottom: 16 }}>
          <RobotOutlined style={{ fontSize: 44, color: "#4f6ef7" }} />
          <Title level={3} style={{ margin: "8px 0 0" }}>
            Copilot-Lite
          </Title>
          <Text type="secondary">你的个人 AI 智能助理 · 青木</Text>
        </div>

        <Tabs
          centered
          activeKey={mode}
          onChange={(k) => {
            setMode(k as "login" | "register");
            form.resetFields();
          }}
          items={[
            { key: "login", label: "登 录" },
            { key: "register", label: "注 册" },
          ]}
        />

        <Form form={form} onFinish={submit} size="large">
          <Form.Item
            name="username"
            rules={[
              { required: true, message: "请输入用户名" },
              { min: 2, max: 64, message: "2-64 位字母/数字/下划线" },
              {
                pattern: /^[a-zA-Z0-9_]+$/,
                message: "仅支持字母、数字、下划线",
              },
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[
              { required: true, message: "请输入密码" },
              { min: 6, max: 64, message: "密码至少 6 位" },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码（至少 6 位）"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 8 }}>
            <Button type="primary" htmlType="submit" block loading={loading}>
              {mode === "login" ? "登 录" : "注册并登录"}
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: "center" }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {mode === "login"
              ? "没有账号？切换到「注册」创建"
              : "注册后数据（会话/待办/知识库）仅自己可见"}
          </Text>
        </div>
      </Card>
    </div>
  );
}
