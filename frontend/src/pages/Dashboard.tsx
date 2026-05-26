import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Upload, Activity, FileText, CheckCircle, XCircle, Clock } from 'lucide-react';
import { api, endpoints } from '../api/client';

interface Stats {
  jobs: {
    total: number;
    completed: number;
    failed: number;
    processing: number;
  };
  outputs: {
    tier0: number;
    tier1: number;
    tier2: number;
    track_a: number;
  };
}

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [health, setHealth] = useState<{ status: string; version: string } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statsRes, healthRes] = await Promise.all([
          api.get(endpoints.admin.stats),
          api.get(endpoints.health),
        ]);
        setStats(statsRes.data);
        setHealth(healthRes.data);
      } catch (err) {
        console.error('Failed to fetch dashboard data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        {health && (
          <div className="flex items-center text-sm text-gray-500">
            <span
              className={`w-2 h-2 rounded-full mr-2 ${health.status === 'healthy' ? 'bg-green-500' : 'bg-red-500'}`}
            />
            API v{health.version}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-500">Total Jobs</p>
              <p className="text-2xl font-bold">{stats?.jobs.total || 0}</p>
            </div>
            <FileText className="h-10 w-10 text-blue-500" />
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-500">Completed</p>
              <p className="text-2xl font-bold text-green-600">{stats?.jobs.completed || 0}</p>
            </div>
            <CheckCircle className="h-10 w-10 text-green-500" />
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-500">Processing</p>
              <p className="text-2xl font-bold text-blue-600">{stats?.jobs.processing || 0}</p>
            </div>
            <Clock className="h-10 w-10 text-blue-500" />
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-500">Failed</p>
              <p className="text-2xl font-bold text-red-600">{stats?.jobs.failed || 0}</p>
            </div>
            <XCircle className="h-10 w-10 text-red-500" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Quick Actions</h2>
          <div className="space-y-3">
            <Link
              to="/upload"
              className="flex items-center p-4 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors"
            >
              <Upload className="h-6 w-6 text-blue-600" />
              <div className="ml-4">
                <p className="font-medium text-gray-900">Upload Document</p>
                <p className="text-sm text-gray-500">Process a new clinical document</p>
              </div>
            </Link>
            <Link
              to="/tier-test"
              className="flex items-center p-4 bg-purple-50 rounded-lg hover:bg-purple-100 transition-colors"
            >
              <Activity className="h-6 w-6 text-purple-600" />
              <div className="ml-4">
                <p className="font-medium text-gray-900">Test Individual Tiers</p>
                <p className="text-sm text-gray-500">Test Tier 0, 1, 2, 3, or Tracks separately</p>
              </div>
            </Link>
          </div>
        </div>

        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Output Files</h2>
          <div className="space-y-2">
            {stats && Object.entries(stats.outputs).map(([tier, count]) => (
              <div key={tier} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <span className="font-medium text-gray-700 capitalize">{tier.replace('_', ' ')}</span>
                <span className="text-gray-500">{count} files</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
