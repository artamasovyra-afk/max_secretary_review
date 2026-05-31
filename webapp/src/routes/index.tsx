import { createBrowserRouter } from "react-router-dom";
import { AuthProvider } from "../auth/AuthContext";
import { AppLayout } from "../components/AppLayout";
import { GroupAssignmentDetailsPage } from "../pages/GroupAssignmentDetailsPage";
import { GroupAssignmentsPage } from "../pages/GroupAssignmentsPage";
import { TaskDetailsPage } from "../pages/TaskDetailsPage";
import { TasksPage } from "../pages/TasksPage";
import { SettingsPage } from "../pages/SettingsPage";
import { SuperAdminPage } from "../pages/SuperAdminPage";

export const router = createBrowserRouter([
  {
    path: "/super-admin",
    element: <SuperAdminPage />,
  },
  {
    path: "/",
    element: (
      <AuthProvider>
        <AppLayout />
      </AuthProvider>
    ),
    children: [
      {
        index: true,
        element: <TasksPage />,
      },
      {
        path: "dashboard",
        element: <TasksPage />,
      },
      {
        path: "tasks",
        element: <TasksPage />,
      },
      {
        path: "tasks/:taskId",
        element: <TaskDetailsPage />,
      },
      {
        path: "group-assignments",
        element: <GroupAssignmentsPage />,
      },
      {
        path: "group-assignments/:taskId",
        element: <GroupAssignmentDetailsPage />,
      },
      {
        path: "settings",
        element: <SettingsPage />,
      },
    ],
  },
]);
