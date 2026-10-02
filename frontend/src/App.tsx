import type { ReactNode } from "react";
import { Navigate, NavLink, Outlet, Route, Routes } from "react-router";
import { useAuth } from "./auth";
import Login from "./pages/Login";
import StudentHome from "./pages/student/Home";
import StudentResult from "./pages/student/Result";
import Solve from "./pages/student/Solve";
import TeacherAssignment from "./pages/teacher/AssignmentDetail";
import TeacherHome from "./pages/teacher/Home";
import Problems from "./pages/teacher/Problems";
import Stats from "./pages/teacher/Stats";
import StudentDetail from "./pages/teacher/StudentDetail";
import Students from "./pages/teacher/Students";
import type { Role } from "./types";

function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to={user.role === "teacher" ? "/t" : "/s"} replace />;
  return <>{children}</>;
}

function Home() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === "teacher" ? "/t" : "/s"} replace />;
}

function StudentLayout() {
  const { user, signOut } = useAuth();
  return (
    <div className="page">
      <header className="topbar">
        <NavLink to="/s" className="brand">문법 숙제</NavLink>
        <span className="muted small">{user?.name}</span>
        <button className="btn link small" onClick={signOut}>로그아웃</button>
      </header>
      <Outlet />
    </div>
  );
}

function TeacherLayout() {
  const { signOut } = useAuth();
  return (
    <div className="page wide">
      <header className="topbar">
        <NavLink to="/t" className="brand">선생님</NavLink>
        <button className="btn link small" onClick={signOut}>로그아웃</button>
      </header>
      <nav className="tabs">
        <NavLink to="/t" end>현황</NavLink>
        <NavLink to="/t/students">학생</NavLink>
        <NavLink to="/t/problems">문제</NavLink>
        <NavLink to="/t/stats">통계</NavLink>
      </nav>
      <Outlet />
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Home />} />
      <Route path="/s" element={<RequireRole role="student"><StudentLayout /></RequireRole>}>
        <Route index element={<StudentHome />} />
        <Route path="a/:id" element={<Solve />} />
        <Route path="a/:id/result" element={<StudentResult />} />
      </Route>
      <Route path="/t" element={<RequireRole role="teacher"><TeacherLayout /></RequireRole>}>
        <Route index element={<TeacherHome />} />
        <Route path="a/:id" element={<TeacherAssignment />} />
        <Route path="students" element={<Students />} />
        <Route path="students/:id" element={<StudentDetail />} />
        <Route path="problems" element={<Problems />} />
        <Route path="stats" element={<Stats />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
