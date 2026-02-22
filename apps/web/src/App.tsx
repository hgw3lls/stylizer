import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { Layout } from './components/Layout';
import { HistoryPage } from './pages/HistoryPage';
import { StylePacksPage } from './pages/StylePacksPage';
import { TranslatePage } from './pages/TranslatePage';

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <StylePacksPage /> },
      { path: 'translate', element: <TranslatePage /> },
      { path: 'history', element: <HistoryPage /> },
    ],
  },
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
