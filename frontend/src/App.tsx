import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import AssetDetail from './pages/AssetDetail'
import Dashboard from './pages/Dashboard'
import Holdings from './pages/Holdings'
import Performance from './pages/Performance'
import Transactions from './pages/Transactions'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="holdings" element={<Holdings />} />
        <Route path="transactions" element={<Transactions />} />
        <Route path="performance" element={<Performance />} />
        <Route path="asset/:symbol/:assetType" element={<AssetDetail />} />
      </Route>
    </Routes>
  )
}
