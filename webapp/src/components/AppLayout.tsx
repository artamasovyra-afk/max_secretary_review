import {
  MenuOutlined,
  SettingOutlined,
  TeamOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Alert, Button, Dropdown, Empty, Layout, Menu, Space, Spin, Typography } from "antd";
import type { MenuProps } from "antd";
import { useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { appDisplayName, navigationLabels } from "../navigation/menuItems";

const { Header, Sider, Content } = Layout;

const menuItems: MenuProps["items"] = [
  {
    key: "/tasks",
    icon: <UnorderedListOutlined />,
    label: navigationLabels.tasks,
  },
  {
    key: "/group-assignments",
    icon: <TeamOutlined />,
    label: navigationLabels.groupAssignments,
  },
  {
    key: "/settings",
    icon: <SettingOutlined />,
    label: navigationLabels.settings,
  },
];

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const auth = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const canUseGroupAssignments = auth.roles.includes("super_admin")
    || auth.availableChats.some((chat) => chat.role === "chat_admin" || chat.role === "super_admin");
  const visibleMenuItems = useMemo(
    () => (menuItems ?? []).filter((item) => item?.key !== "/group-assignments" || canUseGroupAssignments),
    [canUseGroupAssignments],
  );
  const selectedKey = location.pathname.startsWith("/tasks")
    ? "/tasks"
    : location.pathname.startsWith("/group-assignments")
      ? "/group-assignments"
    : location.pathname.startsWith("/settings")
      ? "/settings"
      : "/tasks";

  const handleMenuClick: MenuProps["onClick"] = ({ key }) => {
    setMobileMenuOpen(false);
    navigate(auth.withAuthSearch(key));
  };

  const content = auth.loading ? (
    <AuthLoadingState />
  ) : auth.authenticated ? (
    <Outlet />
  ) : (
    <AuthUnauthorizedState error={auth.error} />
  );

  return (
    <Layout className="app-shell">
      <Sider className="app-sider" breakpoint="lg" collapsedWidth={0} width={240}>
        <div className="app-brand">
          <img className="app-brand-logo" src="/brand/dyak-mark.png" alt={appDisplayName} />
          <Typography.Text className="app-brand-title" strong>
            {appDisplayName}
          </Typography.Text>
        </div>
        <Menu
          className="app-menu"
          mode="inline"
          items={visibleMenuItems}
          selectedKeys={[selectedKey]}
          onClick={handleMenuClick}
        />
      </Sider>
      <Layout className="app-main-layout">
        <Header className="app-header">
          <div className="app-mobile-header-row">
            <Dropdown
              open={mobileMenuOpen}
              onOpenChange={setMobileMenuOpen}
              trigger={["click"]}
              placement="bottomLeft"
              overlayClassName="app-mobile-menu-dropdown"
              menu={{
                items: visibleMenuItems,
                onClick: handleMenuClick,
                selectable: true,
                selectedKeys: [selectedKey],
              }}
            >
              <Button
                aria-label="Открыть меню"
                className="app-mobile-menu-button"
                type="text"
                icon={<MenuOutlined />}
              />
            </Dropdown>
            <img className="app-mobile-header-logo" src="/brand/dyak-mark.png" alt="" aria-hidden="true" />
            <Typography.Text className="app-mobile-header-title" strong>
              {appDisplayName}
            </Typography.Text>
          </div>
          <Space className="app-header-copy" direction="vertical" size={0}>
            <Typography.Text className="app-header-title" strong>
              {appDisplayName}
            </Typography.Text>
            <Typography.Text className="app-header-subtitle" type="secondary">
              Центр управления задачами
            </Typography.Text>
          </Space>
        </Header>
        <Content className="app-content">
          {auth.devWarning ? (
            <Alert
              className="auth-dev-warning"
              type="warning"
              showIcon
              message={auth.devWarning}
            />
          ) : null}
          {content}
        </Content>
      </Layout>
    </Layout>
  );
}

function AuthLoadingState() {
  return (
    <div className="auth-state">
      <Spin size="large" />
      <Typography.Text type="secondary">Проверяем вход…</Typography.Text>
    </div>
  );
}

function AuthUnauthorizedState({ error }: { error: string | null }) {
  return (
    <div className="auth-state">
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <Space direction="vertical" size={6}>
            <Typography.Title level={3}>Откройте WebApp из MAX</Typography.Title>
            <Typography.Text type="secondary">
              Для доступа к задачам откройте Дьяк из чата MAX. Так мы поймём, кто вы, и покажем ваши задачи.
            </Typography.Text>
            {error ? <Alert type="warning" showIcon message={error} /> : null}
          </Space>
        }
      >
        <Button onClick={() => window.location.reload()}>Повторить вход</Button>
      </Empty>
    </div>
  );
}
