"use client";
import { create } from "zustand";
import { api } from "@/lib/api";

interface AuthState {
  token: string | null;
  tenantId: string | null;
  role: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  init: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  token: null,
  tenantId: null,
  role: null,

  init: () => {
    const token = localStorage.getItem("access_token");
    const tenantId = localStorage.getItem("tenant_id");
    const role = localStorage.getItem("role");
    if (token) set({ token, tenantId, role });
  },

  login: async (email, password) => {
    const form = new FormData();
    form.append("username", email);
    form.append("password", password);
    const { data } = await api.post("/auth/login", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("tenant_id", data.tenant_id);
    localStorage.setItem("role", data.role);
    set({ token: data.access_token, tenantId: data.tenant_id, role: data.role });
  },

  logout: () => {
    localStorage.clear();
    set({ token: null, tenantId: null, role: null });
    window.location.href = "/login";
  },
}));
