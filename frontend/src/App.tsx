import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Allocation from './pages/Allocation'
import AssetDetail from './pages/AssetDetail'
import Dashboard from './pages/Dashboard'
import Holdings from './pages/Holdings'
import Performance from './pages/Performance'
import Settings from './pages/Settings'
import Transactions from './pages/Transactions'
import YearInReview from './pages/YearInReview'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="holdings" element={<Holdings />} />
        <Route path="allocation" element={<Allocation />} />
        <Route path="performance" element={<Performance />} />
        <Route path="transactions" element={<Transactions />} />
        <Route path="settings" element={<Settings />} />
        <Route path="asset/:symbol/:assetType" element={<AssetDetail />} />
        <Route path="year/:year" element={<YearInReview />} />
        <Route path="year" element={<YearInReview />} />
      </Route>
    </Routes>
  )
}
