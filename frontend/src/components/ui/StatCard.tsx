interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  trend?: "up" | "down" | "neutral";
}

export default function StatCard({ label, value, sub, trend }: StatCardProps) {
  return (
    <div className="card">
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-2xl font-bold mt-1 text-white">{value}</p>
      {sub && (
        <p className={`text-xs mt-1 ${
          trend === "up" ? "text-green-400" :
          trend === "down" ? "text-red-400" : "text-gray-500"
        }`}>{sub}</p>
      )}
    </div>
  );
}
