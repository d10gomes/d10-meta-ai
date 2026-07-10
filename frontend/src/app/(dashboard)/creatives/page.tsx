"use client";

import { useRef, useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Upload, Image as ImageIcon, Film, Search,
  Trash2, RefreshCw, ExternalLink, CheckCircle2, Clock, AlertCircle,
  TrendingUp, Eye, Zap,
} from "lucide-react";
import { clsx } from "clsx";
import { toast } from "sonner";
import { useApi } from "@/hooks/useApi";

// ─── Types ──────────────────────────────────────────────────────────────────

interface MediaAsset {
  id: string;
  name: string;
  original_name: string;
  file_type: "image" | "video" | "gif";
  format: "feed" | "story" | "reels" | "carousel" | "unknown";
  mime_type: string;
  file_size_mb: number;
  width_px?: number;
  height_px?: number;
  duration_secs?: number;
  public_url: string;
  meta_image_hash?: string;
  meta_video_id?: string;
  meta_status?: string;
  meta_synced_at?: string;
  offer_id?: string;
  tags: string[];
  notes?: string;
  avg_ctr?: number;
  avg_roas?: number;
  avg_cpa?: number;
  avg_frequency?: number;
  times_used: number;
  performance_score?: number;
  status: "uploading" | "ready" | "synced_meta" | "error" | "deleted";
  created_at: string;
}

interface Stats {
  total: number;
  images: number;
  videos: number;
  synced_meta: number;
  total_gb: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const FORMAT_LABELS: Record<string, string> = {
  feed: "Feed",
  story: "Stories",
  reels: "Reels",
  carousel: "Carrossel",
  unknown: "—",
};

const STATUS_CONFIG: Record<string, { label: string; icon: typeof CheckCircle2; color: string }> = {
  ready: { label: "Pronto", icon: CheckCircle2, color: "text-emerald-400" },
  synced_meta: { label: "No Meta", icon: CheckCircle2, color: "text-brand-400" },
  uploading: { label: "Enviando", icon: Clock, color: "text-yellow-400" },
  error: { label: "Erro", icon: AlertCircle, color: "text-red-400" },
  deleted: { label: "Deletado", icon: Trash2, color: "text-gray-500" },
};

function scoreColor(score?: number) {
  if (!score) return "text-gray-500";
  if (score >= 7) return "text-emerald-400";
  if (score >= 4) return "text-yellow-400";
  return "text-red-400";
}

// ─── Upload Zone ─────────────────────────────────────────────────────────────

function UploadZone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handle = useCallback(
    (files: FileList | null) => {
      if (!files) return;
      const valid = Array.from(files).filter((f) =>
        /^(image\/(jpeg|png|gif|webp)|video\/(mp4|quicktime|webm))$/.test(f.type)
      );
      if (valid.length) onFiles(valid);
    },
    [onFiles]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        handle(e.dataTransfer.files);
      }}
      onClick={() => inputRef.current?.click()}
      className={clsx(
        "border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors",
        dragging
          ? "border-brand-400 bg-brand-500/10"
          : "border-surface-border hover:border-brand-500/50 hover:bg-surface-border/30"
      )}
    >
      <Upload className="mx-auto mb-3 text-gray-500" size={32} />
      <p className="text-sm text-gray-400">
        Arraste imagens e vídeos aqui ou{" "}
        <span className="text-brand-400 font-medium">clique para selecionar</span>
      </p>
      <p className="text-xs text-gray-600 mt-1">
        JPG, PNG, GIF, WebP, MP4, MOV · Imagens até 30 MB · Vídeos até 500 MB
      </p>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime,video/webm"
        className="hidden"
        onChange={(e) => handle(e.target.files)}
      />
    </div>
  );
}

// ─── Asset Card ──────────────────────────────────────────────────────────────

function AssetCard({
  asset,
  onDelete,
  onSyncMeta,
}: {
  asset: MediaAsset;
  onDelete: (id: string) => void;
  onSyncMeta: (id: string) => void;
}) {
  const [hover, setHover] = useState(false);
  const statusCfg = STATUS_CONFIG[asset.status] ?? STATUS_CONFIG.error;
  const StatusIcon = statusCfg.icon;

  return (
    <div
      className="bg-surface-card border border-surface-border rounded-xl overflow-hidden"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {/* Thumbnail */}
      <div className="relative bg-gray-900 aspect-video flex items-center justify-center overflow-hidden">
        {asset.file_type === "video" ? (
          <div className="flex flex-col items-center gap-2 text-gray-600">
            <Film size={36} />
            {asset.duration_secs && (
              <span className="text-xs text-gray-500">{Math.round(asset.duration_secs)}s</span>
            )}
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={asset.public_url}
            alt={asset.name}
            className="w-full h-full object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        )}

        {/* Hover overlay */}
        {hover && (
          <div className="absolute inset-0 bg-black/60 flex items-center justify-center gap-2">
            <a
              href={asset.public_url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="p-2 bg-white/10 rounded-lg hover:bg-white/20 text-white"
            >
              <ExternalLink size={16} />
            </a>
            {asset.status === "ready" && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onSyncMeta(asset.id);
                }}
                className="p-2 bg-white/10 rounded-lg hover:bg-white/20 text-white"
                title="Sincronizar com Meta"
              >
                <RefreshCw size={16} />
              </button>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(asset.id);
              }}
              className="p-2 bg-red-500/20 rounded-lg hover:bg-red-500/40 text-red-400"
            >
              <Trash2 size={16} />
            </button>
          </div>
        )}

        {/* Badges */}
        <span className="absolute top-2 left-2 text-[10px] bg-black/60 text-gray-300 px-1.5 py-0.5 rounded font-mono">
          {FORMAT_LABELS[asset.format] ?? asset.format}
        </span>
        <span className="absolute top-2 right-2">
          {asset.file_type === "video" ? (
            <Film size={14} className="text-brand-400" />
          ) : (
            <ImageIcon size={14} className="text-gray-400" />
          )}
        </span>
      </div>

      {/* Info */}
      <div className="p-3 space-y-2">
        <p className="text-sm font-medium text-white truncate" title={asset.name}>
          {asset.name}
        </p>

        <div className="flex items-center justify-between">
          <div className={clsx("flex items-center gap-1 text-xs", statusCfg.color)}>
            <StatusIcon size={11} />
            {statusCfg.label}
          </div>
          <span className="text-xs text-gray-600">{asset.file_size_mb} MB</span>
        </div>

        {/* Metrics row */}
        {(asset.avg_ctr != null || asset.avg_roas != null || asset.performance_score != null) && (
          <div className="flex gap-3 pt-1 border-t border-surface-border">
            {asset.avg_ctr != null && (
              <div className="flex items-center gap-1 text-xs text-gray-400">
                <Eye size={10} />
                {(asset.avg_ctr * 100).toFixed(1)}%
              </div>
            )}
            {asset.avg_roas != null && (
              <div className="flex items-center gap-1 text-xs text-gray-400">
                <TrendingUp size={10} />
                {asset.avg_roas.toFixed(1)}x
              </div>
            )}
            {asset.performance_score != null && (
              <div
                className={clsx(
                  "flex items-center gap-1 text-xs ml-auto font-mono",
                  scoreColor(asset.performance_score)
                )}
              >
                <Zap size={10} />
                {asset.performance_score.toFixed(1)}
              </div>
            )}
          </div>
        )}

        {/* Tags */}
        {asset.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {asset.tags.slice(0, 3).map((t) => (
              <span
                key={t}
                className="text-[10px] bg-surface-border text-gray-400 px-1.5 py-0.5 rounded-full"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function CreativesPage() {
  const api = useApi();
  const qc = useQueryClient();

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [formatFilter, setFormatFilter] = useState("");
  const [sort, setSort] = useState("created_at");
  const [uploading, setUploading] = useState<string[]>([]);

  const statsQ = useQuery<Stats>({
    queryKey: ["media-stats"],
    queryFn: () => api.get("/media/stats").then((r) => r.data),
    refetchInterval: 30_000,
  });

  const listQ = useQuery<{ total: number; items: MediaAsset[] }>({
    queryKey: ["media-list", search, typeFilter, formatFilter, sort],
    queryFn: () =>
      api
        .get("/media", {
          params: {
            search: search || undefined,
            file_type: typeFilter || undefined,
            format: formatFilter || undefined,
            sort,
            limit: 100,
          },
        })
        .then((r) => r.data),
    refetchInterval: 15_000,
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/media/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["media-list"] });
      qc.invalidateQueries({ queryKey: ["media-stats"] });
      toast.success("Mídia removida.");
    },
  });

  const syncMut = useMutation({
    mutationFn: ({ id, accountId }: { id: string; accountId: string }) =>
      api.post(`/media/${id}/sync-meta?meta_account_id=${accountId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["media-list"] });
      toast.success("Sincronizado com o Meta.");
    },
    onError: () => toast.error("Erro ao sincronizar com o Meta."),
  });

  const handleFiles = async (files: File[]) => {
    for (const file of files) {
      setUploading((prev) => [...prev, file.name]);
      try {
        const fd = new FormData();
        fd.append("file", file);
        await api.post("/media/upload", fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        qc.invalidateQueries({ queryKey: ["media-list"] });
        qc.invalidateQueries({ queryKey: ["media-stats"] });
        toast.success(`"${file.name}" enviado!`);
      } catch {
        toast.error(`Erro ao enviar "${file.name}".`);
      } finally {
        setUploading((prev) => prev.filter((n) => n !== file.name));
      }
    }
  };

  const assets = listQ.data?.items ?? [];
  const stats = statsQ.data;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Biblioteca de Criativos</h1>
        <p className="text-sm text-gray-400 mt-1">
          Gerencie imagens e vídeos para seus anúncios no Meta
        </p>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {[
            { label: "Total", value: stats.total },
            { label: "Imagens", value: stats.images },
            { label: "Vídeos", value: stats.videos },
            { label: "No Meta", value: stats.synced_meta },
            { label: "Armazenamento", value: `${stats.total_gb} GB` },
          ].map(({ label, value }) => (
            <div
              key={label}
              className="bg-surface-card border border-surface-border rounded-xl p-4 text-center"
            >
              <p className="text-xl font-bold text-white">{value}</p>
              <p className="text-xs text-gray-500 mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Upload */}
      <UploadZone onFiles={handleFiles} />

      {/* Upload progress */}
      {uploading.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {uploading.map((name) => (
            <div
              key={name}
              className="flex items-center gap-2 bg-brand-500/10 border border-brand-500/20 rounded-full px-3 py-1.5 text-xs text-brand-400"
            >
              <RefreshCw size={11} className="animate-spin" />
              {name}
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar criativos..."
            className="w-full pl-9 pr-4 py-2 bg-surface-card border border-surface-border rounded-lg text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500"
          />
        </div>

        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="bg-surface-card border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-400 focus:outline-none focus:border-brand-500"
        >
          <option value="">Todos os tipos</option>
          <option value="image">Imagens</option>
          <option value="video">Vídeos</option>
          <option value="gif">GIFs</option>
        </select>

        <select
          value={formatFilter}
          onChange={(e) => setFormatFilter(e.target.value)}
          className="bg-surface-card border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-400 focus:outline-none focus:border-brand-500"
        >
          <option value="">Todos os formatos</option>
          <option value="feed">Feed</option>
          <option value="story">Stories</option>
          <option value="reels">Reels</option>
          <option value="carousel">Carrossel</option>
        </select>

        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="bg-surface-card border border-surface-border rounded-lg px-3 py-2 text-sm text-gray-400 focus:outline-none focus:border-brand-500"
        >
          <option value="created_at">Mais recentes</option>
          <option value="avg_ctr">Maior CTR</option>
          <option value="avg_roas">Maior ROAS</option>
          <option value="times_used">Mais usados</option>
        </select>
      </div>

      {/* Grid */}
      {listQ.isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {Array.from({ length: 10 }).map((_, i) => (
            <div
              key={i}
              className="bg-surface-card border border-surface-border rounded-xl overflow-hidden animate-pulse"
            >
              <div className="bg-gray-800 aspect-video" />
              <div className="p-3 space-y-2">
                <div className="h-3 bg-gray-800 rounded w-3/4" />
                <div className="h-2 bg-gray-800 rounded w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : assets.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <ImageIcon size={48} className="mx-auto mb-4 opacity-30" />
          <p className="text-sm">Nenhum criativo encontrado.</p>
          <p className="text-xs mt-1">Faça upload de imagens ou vídeos acima.</p>
        </div>
      ) : (
        <>
          <p className="text-xs text-gray-500">{listQ.data?.total ?? 0} criativos</p>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {assets.map((asset) => (
              <AssetCard
                key={asset.id}
                asset={asset}
                onDelete={(id) => {
                  if (confirm("Remover este criativo da biblioteca?")) {
                    deleteMut.mutate(id);
                  }
                }}
                onSyncMeta={(id) => syncMut.mutate({ id, accountId: "" })}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
