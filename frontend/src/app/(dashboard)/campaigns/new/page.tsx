"use client";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ArrowLeft, ArrowRight, CheckCircle2, Loader2, Upload, X, AlertCircle } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

type Objective = {
  key: string;
  label: string;
  icon: string;
  description: string;
};

type MetaAccount = {
  id: string;
  ad_account_id: string;
  name: string;
};

type Page = {
  id: string;
  name: string;
};

type WizardState = {
  // Step 1
  objective: string;
  // Step 2
  accountId: string;
  campaignName: string;
  dailyBudgetBrl: number;
  // Step 3
  ageMin: number;
  ageMax: number;
  genders: string[];   // [] = ambos, ["men"], ["women"]
  countries: string[];
  // Step 4
  pageId: string;
  headline: string;
  body: string;
  linkUrl: string;
  ctaLabel: string;
  // Step 5 (image)
  imageHash: string;
  imagePreview: string;
};

const INITIAL: WizardState = {
  objective: "",
  accountId: "",
  campaignName: "",
  dailyBudgetBrl: 50,
  ageMin: 18,
  ageMax: 65,
  genders: [],
  countries: ["BR"],
  pageId: "",
  headline: "",
  body: "",
  linkUrl: "",
  ctaLabel: "Saiba mais",
  imageHash: "",
  imagePreview: "",
};

const STEPS = [
  "Objetivo",
  "Orçamento",
  "Público",
  "Anúncio",
  "Imagem",
  "Revisão",
];

const CTA_OPTIONS = [
  "Saiba mais",
  "Comprar agora",
  "Entre em contato",
  "Cadastrar-se",
  "Inscrever-se",
  "Solicitar orçamento",
];

const BUDGET_TIPS: [number, string][] = [
  [6,   "Mínimo aceito pelo Meta — aprendizado muito lento"],
  [30,  "Bom para começar e testar"],
  [100, "Recomendado para resultados consistentes"],
  [300, "Escala — bom para campanhas consolidadas"],
];

// ── Helper components ─────────────────────────────────────────────────────────

function StepHeader({ step, state }: { step: number; state: WizardState }) {
  return (
    <div className="mb-8">
      <div className="flex gap-2 mb-4">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-1.5">
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                i + 1 < step
                  ? "bg-green-600 text-white"
                  : i + 1 === step
                  ? "bg-brand-500 text-white"
                  : "bg-gray-700 text-gray-500"
              }`}
            >
              {i + 1 < step ? <CheckCircle2 size={14} /> : i + 1}
            </div>
            <span className={`text-xs hidden sm:inline ${i + 1 === step ? "text-white font-medium" : "text-gray-500"}`}>
              {label}
            </span>
            {i < STEPS.length - 1 && <div className="w-6 h-px bg-gray-700 mx-1" />}
          </div>
        ))}
      </div>
      <h2 className="text-xl font-bold text-white">
        {step === 1 && "Qual é o seu objetivo?"}
        {step === 2 && "Quanto quer investir por dia?"}
        {step === 3 && "Para quem é esse anúncio?"}
        {step === 4 && "O que o anúncio vai dizer?"}
        {step === 5 && "Adicione uma imagem (opcional)"}
        {step === 6 && "Revisão — tudo certo?"}
      </h2>
      <p className="text-gray-400 text-sm mt-1">
        {step === 1 && "Escolha o que você quer alcançar com essa campanha."}
        {step === 2 && "Quanto você quer gastar por dia nessa campanha."}
        {step === 3 && "Configure quem vai ver o seu anúncio."}
        {step === 4 && "Escreva o texto do seu anúncio. Seja direto e claro."}
        {step === 5 && "Uma boa imagem aumenta muito a taxa de cliques. Pode pular se não tiver agora."}
        {step === 6 && "Revise tudo antes de criar. A campanha será criada pausada — você ativa quando quiser."}
      </p>
    </div>
  );
}

function FieldError({ msg }: { msg: string }) {
  return (
    <p className="text-red-400 text-xs mt-1 flex items-center gap-1">
      <AlertCircle size={11} /> {msg}
    </p>
  );
}

// ── Main wizard ───────────────────────────────────────────────────────────────

export default function NewCampaignPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [state, setState] = useState<WizardState>(INITIAL);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [uploadLoading, setUploadLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const set = (patch: Partial<WizardState>) => setState((s) => ({ ...s, ...patch }));

  // Data fetches
  const { data: objectives = [] } = useQuery<Objective[]>({
    queryKey: ["objectives"],
    queryFn: () => api.get("/campaigns/objectives").then((r) => r.data),
  });

  const { data: accounts = [] } = useQuery<MetaAccount[]>({
    queryKey: ["meta-accounts"],
    queryFn: () => api.get("/meta-accounts").then((r) => r.data),
  });

  const { data: pages = [] } = useQuery<Page[]>({
    queryKey: ["pages", state.accountId],
    queryFn: () => api.get(`/campaigns/pages?account_id=${state.accountId}`).then((r) => r.data),
    enabled: !!state.accountId && step >= 4,
  });

  // Campaign creation mutation
  const createMutation = useMutation({
    mutationFn: () =>
      api.post("/campaigns/create", {
        account_id: state.accountId,
        campaign_name: state.campaignName,
        objective: state.objective,
        daily_budget_brl: state.dailyBudgetBrl,
        age_min: state.ageMin,
        age_max: state.ageMax,
        genders: state.genders,
        countries: state.countries,
        page_id: state.pageId || undefined,
        headline: state.headline || undefined,
        body: state.body || undefined,
        link_url: state.linkUrl || undefined,
        cta_label: state.ctaLabel,
        image_hash: state.imageHash || undefined,
      }).then((r) => r.data),
    onSuccess: () => {
      router.push("/campaigns?created=1");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || "Erro ao criar campanha. Tente novamente.";
      setCreateError(msg);
    },
  });

  // Image upload
  async function handleImageSelect(file: File) {
    if (!state.accountId) {
      setErrors({ image: "Selecione uma conta de anúncios antes de enviar a imagem." });
      return;
    }
    setUploadLoading(true);
    setErrors({});
    try {
      const form = new FormData();
      form.append("account_id", state.accountId);
      form.append("file", file);
      const { data } = await api.post("/campaigns/upload-image", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const preview = URL.createObjectURL(file);
      set({ imageHash: data.image_hash, imagePreview: preview });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || "Erro ao fazer upload da imagem.";
      setErrors({ image: msg });
    } finally {
      setUploadLoading(false);
    }
  }

  // Validation per step
  function validate(): boolean {
    const e: Record<string, string> = {};
    if (step === 1) {
      if (!state.objective) e.objective = "Selecione um objetivo";
    }
    if (step === 2) {
      if (!state.accountId) e.accountId = "Selecione a conta de anúncios";
      if (!state.campaignName.trim()) e.campaignName = "Digite o nome da campanha";
      if (state.dailyBudgetBrl < 6) e.budget = "Orçamento mínimo é R$ 6,00 por dia";
    }
    if (step === 3) {
      if (state.ageMin >= state.ageMax) e.age = "Idade mínima deve ser menor que a máxima";
    }
    // Steps 4 and 5: ad copy and image are optional
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function next() {
    if (!validate()) return;
    setStep((s) => Math.min(s + 1, 6));
  }

  function back() {
    setErrors({});
    setStep((s) => Math.max(s - 1, 1));
  }

  const selectedObjective = objectives.find((o) => o.key === state.objective);

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Back nav */}
      <button
        onClick={() => router.push("/campaigns")}
        className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors"
      >
        <ArrowLeft size={14} /> Voltar para campanhas
      </button>

      <div className="card">
        <StepHeader step={step} state={state} />

        {/* ── Step 1: Objective ── */}
        {step === 1 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {objectives.map((obj) => (
              <button
                key={obj.key}
                onClick={() => set({ objective: obj.key })}
                className={`text-left p-4 rounded-xl border-2 transition-all ${
                  state.objective === obj.key
                    ? "border-brand-500 bg-brand-500/10"
                    : "border-gray-700 hover:border-gray-500 bg-surface-card"
                }`}
              >
                <span className="text-2xl">{obj.icon}</span>
                <p className="font-semibold text-white mt-2">{obj.label}</p>
                <p className="text-xs text-gray-400 mt-1">{obj.description}</p>
              </button>
            ))}
            {errors.objective && <FieldError msg={errors.objective} />}
          </div>
        )}

        {/* ── Step 2: Budget + Account + Name ── */}
        {step === 2 && (
          <div className="space-y-5">
            {/* Account selector */}
            <div>
              <label className="block text-sm text-gray-300 mb-2">Conta de anúncios</label>
              {accounts.length === 0 ? (
                <p className="text-amber-400 text-sm">
                  Nenhuma conta conectada.{" "}
                  <a href="/accounts" className="underline">Conectar conta →</a>
                </p>
              ) : (
                <select
                  value={state.accountId}
                  onChange={(e) => set({ accountId: e.target.value })}
                  className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-brand-500"
                >
                  <option value="">Selecione a conta...</option>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name || a.ad_account_id}
                    </option>
                  ))}
                </select>
              )}
              {errors.accountId && <FieldError msg={errors.accountId} />}
            </div>

            {/* Campaign name */}
            <div>
              <label className="block text-sm text-gray-300 mb-2">Nome da campanha</label>
              <input
                type="text"
                value={state.campaignName}
                onChange={(e) => set({ campaignName: e.target.value })}
                placeholder={`Ex: ${selectedObjective?.label || "Campanha"} — Junho 2025`}
                className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-brand-500"
              />
              {errors.campaignName && <FieldError msg={errors.campaignName} />}
            </div>

            {/* Daily budget */}
            <div>
              <label className="block text-sm text-gray-300 mb-2">
                Orçamento diário:{" "}
                <span className="text-brand-400 font-bold text-base">
                  R$ {state.dailyBudgetBrl.toFixed(0)}
                </span>
              </label>
              <input
                type="range"
                min={6}
                max={1000}
                step={1}
                value={state.dailyBudgetBrl}
                onChange={(e) => set({ dailyBudgetBrl: Number(e.target.value) })}
                className="w-full accent-brand-500"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>R$ 6</span><span>R$ 1.000</span>
              </div>
              <div className="mt-3 space-y-1.5">
                {BUDGET_TIPS.map(([amount, tip]) => (
                  <div
                    key={amount}
                    className={`flex items-start gap-2 text-xs p-2 rounded-lg cursor-pointer transition-colors ${
                      state.dailyBudgetBrl >= amount && (BUDGET_TIPS.find(([a]) => a > state.dailyBudgetBrl)?.[0] ?? Infinity) > amount
                        ? "bg-brand-500/10 border border-brand-500/30"
                        : "text-gray-500"
                    }`}
                    onClick={() => set({ dailyBudgetBrl: amount })}
                  >
                    <span className="font-semibold text-white min-w-[52px]">R$ {amount}</span>
                    <span>{tip}</span>
                  </div>
                ))}
              </div>
              {errors.budget && <FieldError msg={errors.budget} />}
            </div>
          </div>
        )}

        {/* ── Step 3: Audience ── */}
        {step === 3 && (
          <div className="space-y-5">
            {/* Age range */}
            <div>
              <label className="block text-sm text-gray-300 mb-3">
                Faixa de idade: <span className="text-white font-bold">{state.ageMin} – {state.ageMax} anos</span>
              </label>
              <div className="flex gap-4">
                <div className="flex-1">
                  <p className="text-xs text-gray-500 mb-1">Mínimo</p>
                  <select
                    value={state.ageMin}
                    onChange={(e) => set({ ageMin: Number(e.target.value) })}
                    className="w-full bg-surface border border-surface-border rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
                  >
                    {[13, 18, 21, 25, 30, 35, 40, 45, 50, 55, 60].map((a) => (
                      <option key={a} value={a}>{a} anos</option>
                    ))}
                  </select>
                </div>
                <div className="flex-1">
                  <p className="text-xs text-gray-500 mb-1">Máximo</p>
                  <select
                    value={state.ageMax}
                    onChange={(e) => set({ ageMax: Number(e.target.value) })}
                    className="w-full bg-surface border border-surface-border rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
                  >
                    {[18, 21, 25, 30, 35, 40, 45, 50, 55, 60, 65].map((a) => (
                      <option key={a} value={a}>{a} anos</option>
                    ))}
                  </select>
                </div>
              </div>
              {errors.age && <FieldError msg={errors.age} />}
            </div>

            {/* Gender */}
            <div>
              <label className="block text-sm text-gray-300 mb-3">Gênero</label>
              <div className="flex gap-3">
                {[
                  { key: "all",   label: "Todos" },
                  { key: "men",   label: "Homens" },
                  { key: "women", label: "Mulheres" },
                ].map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => set({ genders: key === "all" ? [] : [key] })}
                    className={`flex-1 py-2.5 rounded-xl border-2 text-sm font-medium transition-colors ${
                      (key === "all" && state.genders.length === 0) ||
                      (state.genders.length === 1 && state.genders[0] === key)
                        ? "border-brand-500 bg-brand-500/10 text-white"
                        : "border-gray-700 text-gray-400 hover:border-gray-500"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Country */}
            <div className="bg-surface-border/20 rounded-xl p-3">
              <p className="text-sm text-gray-300">
                🇧🇷 País: <strong className="text-white">Brasil</strong>
              </p>
              <p className="text-xs text-gray-500 mt-0.5">Segmentação por cidade e estado estará disponível em breve.</p>
            </div>
          </div>
        )}

        {/* ── Step 4: Ad Copy ── */}
        {step === 4 && (
          <div className="space-y-5">
            <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-3 text-xs text-amber-300">
              Esta etapa é <strong>opcional</strong>. Se não tiver o texto agora, pule — a campanha será criada sem anúncio e você pode adicionar depois no Meta Ads Manager.
            </div>

            {/* Page selector */}
            {pages.length > 0 && (
              <div>
                <label className="block text-sm text-gray-300 mb-2">Página do Facebook</label>
                <select
                  value={state.pageId}
                  onChange={(e) => set({ pageId: e.target.value })}
                  className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:border-brand-500"
                >
                  <option value="">Selecione a página...</option>
                  {pages.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
            )}

            <div>
              <label className="block text-sm text-gray-300 mb-2">Título do anúncio</label>
              <input
                type="text"
                value={state.headline}
                onChange={(e) => set({ headline: e.target.value })}
                maxLength={40}
                placeholder="Ex: Oferta especial para você!"
                className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-brand-500"
              />
              <p className="text-xs text-gray-600 mt-1">{state.headline.length}/40 caracteres</p>
            </div>

            <div>
              <label className="block text-sm text-gray-300 mb-2">Texto principal</label>
              <textarea
                value={state.body}
                onChange={(e) => set({ body: e.target.value })}
                maxLength={125}
                rows={3}
                placeholder="Ex: Aproveite nossa promoção exclusiva. Clique e saiba mais!"
                className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-brand-500 resize-none"
              />
              <p className="text-xs text-gray-600 mt-1">{state.body.length}/125 caracteres</p>
            </div>

            <div>
              <label className="block text-sm text-gray-300 mb-2">Link de destino</label>
              <input
                type="url"
                value={state.linkUrl}
                onChange={(e) => set({ linkUrl: e.target.value })}
                placeholder="https://seusite.com.br/oferta"
                className="w-full bg-surface border border-surface-border rounded-lg px-4 py-2.5 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-brand-500"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-300 mb-2">Botão de ação</label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {CTA_OPTIONS.map((cta) => (
                  <button
                    key={cta}
                    onClick={() => set({ ctaLabel: cta })}
                    className={`py-2 px-3 rounded-lg border text-xs font-medium transition-colors ${
                      state.ctaLabel === cta
                        ? "border-brand-500 bg-brand-500/10 text-white"
                        : "border-gray-700 text-gray-400 hover:border-gray-500"
                    }`}
                  >
                    {cta}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── Step 5: Image ── */}
        {step === 5 && (
          <div className="space-y-4">
            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleImageSelect(f);
              }}
            />

            {state.imagePreview ? (
              <div className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={state.imagePreview}
                  alt="Preview"
                  className="w-full max-h-64 object-cover rounded-xl border border-gray-700"
                />
                <button
                  onClick={() => set({ imageHash: "", imagePreview: "" })}
                  className="absolute top-2 right-2 bg-gray-900/80 text-white p-1.5 rounded-full hover:bg-red-600 transition-colors"
                >
                  <X size={14} />
                </button>
                <p className="text-xs text-green-400 mt-2 flex items-center gap-1">
                  <CheckCircle2 size={12} /> Imagem enviada com sucesso
                </p>
              </div>
            ) : (
              <button
                onClick={() => fileRef.current?.click()}
                disabled={uploadLoading}
                className="w-full border-2 border-dashed border-gray-600 hover:border-brand-500 rounded-xl p-10 flex flex-col items-center gap-3 transition-colors group"
              >
                {uploadLoading ? (
                  <Loader2 size={28} className="text-brand-400 animate-spin" />
                ) : (
                  <Upload size={28} className="text-gray-500 group-hover:text-brand-400 transition-colors" />
                )}
                <div className="text-center">
                  <p className="text-sm font-medium text-gray-300">
                    {uploadLoading ? "Enviando..." : "Clique para selecionar uma imagem"}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">JPG ou PNG — mínimo 600×314 px — máximo 30 MB</p>
                </div>
              </button>
            )}

            {errors.image && <FieldError msg={errors.image} />}

            <div className="text-center">
              <p className="text-xs text-gray-500">
                Sem imagem? <button onClick={next} className="text-brand-400 underline">Pule esta etapa →</button>
              </p>
            </div>
          </div>
        )}

        {/* ── Step 6: Review ── */}
        {step === 6 && (
          <div className="space-y-4">
            {createError && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-sm text-red-300">
                <p className="font-semibold">Erro ao criar campanha</p>
                <p className="mt-1">{createError}</p>
              </div>
            )}

            <div className="space-y-3">
              <ReviewRow icon="🎯" label="Objetivo" value={selectedObjective?.label || state.objective} />
              <ReviewRow icon="🏢" label="Conta" value={accounts.find((a) => a.id === state.accountId)?.name || state.accountId} />
              <ReviewRow icon="📝" label="Nome da campanha" value={state.campaignName} />
              <ReviewRow
                icon="💰"
                label="Orçamento diário"
                value={`R$ ${state.dailyBudgetBrl.toFixed(0)}/dia (R$ ${(state.dailyBudgetBrl * 30).toFixed(0)}/mês estimado)`}
              />
              <ReviewRow
                icon="👥"
                label="Público"
                value={[
                  `${state.ageMin}–${state.ageMax} anos`,
                  state.genders.length === 0 ? "Todos os gêneros" : state.genders.includes("men") ? "Homens" : "Mulheres",
                  "Brasil",
                ].join(" · ")}
              />
              {state.headline && <ReviewRow icon="💬" label="Título do anúncio" value={state.headline} />}
              {state.linkUrl && <ReviewRow icon="🔗" label="Link" value={state.linkUrl} />}
              {state.imageHash
                ? <ReviewRow icon="🖼️" label="Imagem" value="✅ Enviada" />
                : <ReviewRow icon="🖼️" label="Imagem" value="Sem imagem — adicione depois no Meta Ads Manager" />
              }
            </div>

            <div className="bg-green-500/5 border border-green-500/20 rounded-xl p-4 mt-4">
              <p className="text-sm text-green-300 font-semibold">🔒 Campanha criada PAUSADA</p>
              <p className="text-xs text-gray-400 mt-1">
                Nenhum centavo será gasto até você ativar manualmente. Você pode revisar tudo no Meta Ads Manager antes de ativar.
              </p>
            </div>
          </div>
        )}

        {/* ── Navigation ── */}
        <div className="flex justify-between mt-8 pt-4 border-t border-surface-border">
          <button
            onClick={back}
            disabled={step === 1}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-gray-700 text-sm text-gray-400 hover:text-white hover:border-gray-500 disabled:opacity-30 transition-colors"
          >
            <ArrowLeft size={14} /> Voltar
          </button>

          {step < 6 ? (
            <button
              onClick={next}
              className="flex items-center gap-2 btn-primary"
            >
              {step === 5 && !state.imageHash ? "Pular e revisar" : "Próximo"}
              <ArrowRight size={14} />
            </button>
          ) : (
            <button
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending}
              className="flex items-center gap-2 bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white font-semibold px-6 py-2.5 rounded-lg transition-colors"
            >
              {createMutation.isPending ? (
                <><Loader2 size={16} className="animate-spin" /> Criando...</>
              ) : (
                <><CheckCircle2 size={16} /> Criar campanha</>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ReviewRow({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div className="flex items-start gap-3 py-2 border-b border-surface-border last:border-0">
      <span className="text-base w-5 flex-shrink-0">{icon}</span>
      <div>
        <p className="text-xs text-gray-500">{label}</p>
        <p className="text-sm text-white mt-0.5">{value}</p>
      </div>
    </div>
  );
}
