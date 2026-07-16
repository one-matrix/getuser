import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ConfigProvider, theme as antdTheme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useState, useEffect } from 'react';
import Layout from './components/Layout';
import AuthGuard from './components/AuthGuard';
import Dashboard from './pages/Dashboard';
import LeadList from './pages/LeadList';
import TaskManager from './pages/TaskManager';
import Settings from './pages/Settings';
import Login from './pages/Login';
import Mine from './pages/Mine';
import XOperations from './pages/XOperations';

function AnimatedRoutes() {
  const location = useLocation();

  return (
    <Routes location={location}>
      <Route path="/" element={<Dashboard />} />
      <Route path="/leads" element={<LeadList />} />
      <Route path="/tasks" element={<TaskManager />} />
      <Route path="/x" element={<XOperations />} />
      {/* 兼容旧路由:自动重定向到新位置 */}
      <Route path="/cookies" element={<Navigate to="/mine" replace />} />
      <Route path="/business" element={<Navigate to="/mine" replace />} />
      <Route path="/analytics" element={<Navigate to="/tasks?tab=analytics" replace />} />
      <Route path="/users" element={<Navigate to="/settings?tab=users" replace />} />
      <Route path="/mine" element={<Mine />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  const [isDark, setIsDark] = useState(() => {
    return localStorage.getItem('theme_mode') === 'dark';
  });

  useEffect(() => {
    localStorage.setItem('theme_mode', isDark ? 'dark' : 'light');
  }, [isDark]);

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: { colorPrimary: '#1677ff' },
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/*"
            element={
              <AuthGuard>
                <Layout isDark={isDark} onThemeChange={setIsDark}>
                  <AnimatedRoutes />
                </Layout>
              </AuthGuard>
            }
          />
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
