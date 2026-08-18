/* App — route table. Public /login; everything else is behind RequireAuth and
 * rendered inside the AppShell layout (sidebar + topbar + <Outlet/>). Screens for
 * chat/quiz/quizzes/review are placeholders until Phase 4–5. */
import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from '@/components/shell/AppShell';
import { useAuth } from '@/lib/auth';
import { KitchenSink } from '@/screens/KitchenSink';
import { LoginScreen } from '@/screens/LoginScreen';
import { NotebooksScreen } from '@/screens/NotebooksScreen';
import { ChatScreen } from '@/screens/student/ChatScreen';
import { QuizScreen } from '@/screens/student/QuizScreen';
import { NotebookDetail } from '@/screens/teacher/NotebookDetail';
import { QuizzesScreen } from '@/screens/teacher/QuizzesScreen';
import { ReviewScreen } from '@/screens/teacher/ReviewScreen';

import type { ReactNode } from 'react';

function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      {/* Dev-only primitive gallery; tree-shaken out of production builds. */}
      {import.meta.env.DEV && <Route path="/__kitchensink" element={<KitchenSink />} />}
      <Route path="/login" element={<LoginScreen />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/notebooks" replace />} />
        <Route path="notebooks" element={<NotebooksScreen />} />
        <Route path="notebooks/:id" element={<NotebookDetail />} />
        <Route path="chat" element={<ChatScreen />} />
        <Route path="quiz" element={<QuizScreen />} />
        <Route path="quizzes" element={<QuizzesScreen />} />
        <Route path="review" element={<ReviewScreen />} />
      </Route>
      <Route path="*" element={<Navigate to="/notebooks" replace />} />
    </Routes>
  );
}
