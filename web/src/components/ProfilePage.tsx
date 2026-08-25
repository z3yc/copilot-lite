import { useEffect, useState } from "react";
import {
  Avatar,
  Button,
  Card,
  Col,
  Form,
  Input,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
  message,
} from "antd";
import {
  ArrowLeftOutlined,
  FileTextOutlined,
  LockOutlined,
  MessageOutlined,
  RobotOutlined,
  TagsOutlined,
} from "@ant-design/icons";
import { changePassword, fetchProfile } from "../api";
import type { Profile } from "../types";

const { Title } = Typography;

interface Props {
  onBack: () => void;
}

export default function ProfilePage({ onBack }: Props) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [changing, setChanging] = useState(false);
  const [pwForm] = Form.useForm();

  useEffect(() => {
    fetchProfile()
      .then(setProfile)
      .catch((err) => message.error(`加载失败: ${err}`))
      .finally(() => setLoading(false));
  }, []);

  const changePw = async (values: { old_password: string; new_password: string }) => {
    setChanging(true);
    try {
      await changePassword(values.old_password, values.new_password);
      message.success("密码已更新");
      pwForm.resetFields();
    } catch (err) {
      message.error(`${err}`);
    } finally {
      setChanging(false);
    }
  };

  if (loading) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Spin />
      </div>
    );
  }

  const stats = profile
    ? [
        { title: "会话", value: profile.session_count, icon: <MessageOutlined /> },
        { title: "消息", value: profile.message_count, icon: <RobotOutlined /> },
        { title: "待办", value: profile.todo_count, icon: <TagsOutlined /> },
        { title: "文档", value: profile.doc_count, icon: <FileTextOutlined /> },
        { title: "知识分块", value: profile.chunk_count, icon: <TagsOutlined /> },
      ]
    : [];

  return (
    <div className="profile-wrap">
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack} style={{ marginBottom: 12 }}>
        返回
      </Button>

      {/* 用户信息卡 */}
      <Card className="profile-card">
        <Space align="center" size={20}>
          <Avatar size={72} style={{ backgroundColor: "#4f6ef7", fontSize: 30 }}>
            {profile?.username?.[0]?.toUpperCase() ?? "U"}
          </Avatar>
          <div>
            <Space size={8} align="center">
              <Title level={3} style={{ margin: 0 }}>
                {profile?.username}
              </Title>
              {profile?.role === "admin" ? (
                <Tag color="gold">管理员</Tag>
              ) : (
                <Tag color="geekblue">用户</Tag>
              )}
            </Space>
            <div className="dim" style={{ marginTop: 4 }}>
              注册于 {profile?.created_at ? new Date(profile.created_at).toLocaleString("zh-CN") : "-"}
            </div>
          </div>
        </Space>
      </Card>

      {/* 统计卡 */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        {stats.map((s) => (
          <Col span={8} key={s.title}>
            <Card size="small">
              <Statistic title={s.title} value={s.value} prefix={s.icon} />
            </Card>
          </Col>
        ))}
      </Row>

      {/* 修改密码 */}
      <Card
        className="profile-card"
        style={{ marginTop: 12 }}
        title={
          <Space>
            <LockOutlined />
            修改密码
          </Space>
        }
      >
        <Form form={pwForm} layout="vertical" style={{ maxWidth: 360 }} onFinish={changePw}>
          <Form.Item
            name="old_password"
            label="原密码"
            rules={[{ required: true, message: "请输入原密码" }]}
          >
            <Input.Password placeholder="原密码" autoComplete="current-password" />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: "请输入新密码" },
              { min: 6, max: 64, message: "至少 6 位" },
            ]}
          >
            <Input.Password placeholder="新密码（至少 6 位）" autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="confirm"
            label="确认新密码"
            dependencies={["new_password"]}
            rules={[
              { required: true, message: "请再次输入新密码" },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue("new_password") === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error("两次输入不一致"));
                },
              }),
            ]}
          >
            <Input.Password placeholder="再次输入新密码" autoComplete="new-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={changing}>
            更新密码
          </Button>
        </Form>
      </Card>
    </div>
  );
}
