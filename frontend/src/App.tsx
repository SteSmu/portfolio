import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Holdings from './pages/Holdings'
import Transactions from './pages/Transactions'
import Performance from './pages/Performance'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="holdings" element={<Holdings />} />
        <Route path="transactions" element={<Transactions />} />
        <Route path="performance" element={<Performance />} />
      </Route>
    </Routes>
  )
}
