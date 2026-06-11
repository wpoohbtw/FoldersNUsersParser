export type AccountStatus = 'valid' | 'warning' | 'invalid' | string;

export type AccountRole = 'Каналы' | 'Чаты' | 'Био' | 'Папка';

export type ApiAccount = {
  account_id: number;
  user_id: number;
  phone: string;
  username: string;
  first_name: string;
  last_name: string;
  bio: string;
  display_name: string;
  geo: string;
  avatar_url: string;
  session_name: string;
  source_type: string;
  portal_user_id: string;
  portal_username: string;
  account_status: AccountStatus;
  checked_at: string;
  created_at: string;
  roles?: AccountRole[];
};

export type ImportJob = {
  job_id: string;
  type: string;
  status: string;
  total: number;
  success: number;
  failed: number;
  created_at: string;
  finished_at: string | null;
};

export type ImportItem = {
  item_id: string;
  filename: string;
  status: string;
  message: string;
  account_id: number | null;
  source_type: string;
  file_format: string;
  user_id: number;
  phone: string;
  username: string;
  first_name: string;
  last_name: string;
  bio: string;
  display_name: string;
  geo: string;
  avatar_url: string;
  staged_session_name: string;
  is_saved: boolean;
  created_at: string;
  updated_at: string;
};

export type PhoneStep = 'code' | 'password' | 'done';

export type PhoneFlowResponse = {
  flow_id?: string;
  job_id: string;
  item_id?: string;
  next_step: PhoneStep;
};

export type ApiFolder = {
  id: string;
  title: string;
  channels: number;
  peers: number;
  updated_at?: string;
};

export type PortalUser = {
  portal_user_id: string;
  portal_username: string;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // keep default detail
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  mediaUrl(path: string) {
    if (!path) {
      return '';
    }
    if (path.startsWith('http')) {
      return path;
    }
    return `${API_BASE}${path}`;
  },
  async listAccounts() {
    return request<{ items: ApiAccount[] }>('/api/v1/accounts');
  },
  async getCurrentUser() {
    return request<PortalUser>('/api/v1/me');
  },
  async checkAccounts(accountIds: number[]) {
    return request<{ checked: number; failed: number }>('/api/v1/accounts/check', {
      method: 'POST',
      body: JSON.stringify({ account_ids: accountIds }),
    });
  },
  async listAccountFolders(accountId: number) {
    return request<{ items: ApiFolder[] }>(`/api/v1/folders/accounts/${accountId}/folders`);
  },
  async refreshAccountFolders(accountId: number) {
    return request<{ items: ApiFolder[] }>(`/api/v1/folders/accounts/${accountId}/folders/refresh`, {
      method: 'POST',
    });
  },
  async uploadSessions(files: File[]) {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    return request<{ job_id: string }>('/api/v1/imports/session/upload', {
      method: 'POST',
      body: formData,
    });
  },
  async startPhoneImport(phone: string) {
    return request<PhoneFlowResponse>('/api/v1/imports/phone/start', {
      method: 'POST',
      body: JSON.stringify({ phone }),
    });
  },
  async submitPhoneCode(flowId: string, code: string) {
    return request<PhoneFlowResponse>('/api/v1/imports/phone/code', {
      method: 'POST',
      body: JSON.stringify({ flow_id: flowId, code }),
    });
  },
  async submitPhonePassword(flowId: string, password: string) {
    return request<PhoneFlowResponse>('/api/v1/imports/phone/password', {
      method: 'POST',
      body: JSON.stringify({ flow_id: flowId, password }),
    });
  },
  async cancelPhoneImport(flowId: string) {
    return request<{ ok: boolean }>('/api/v1/imports/phone/cancel', {
      method: 'POST',
      body: JSON.stringify({ flow_id: flowId }),
    });
  },
  async getImportJob(jobId: string) {
    return request<ImportJob>(`/api/v1/imports/jobs/${jobId}`);
  },
  async getImportItems(jobId: string) {
    return request<{ items: ImportItem[] }>(`/api/v1/imports/jobs/${jobId}/items`);
  },
  async checkImportJob(jobId: string) {
    return request<{ checked: number; failed: number }>(`/api/v1/imports/jobs/${jobId}/check`, {
      method: 'POST',
      body: JSON.stringify({ item_ids: null }),
    });
  },
  async saveImportJob(jobId: string) {
    return request<{ saved: number; failed: number }>(`/api/v1/imports/jobs/${jobId}/save`, {
      method: 'POST',
      body: JSON.stringify({ item_ids: null }),
    });
  },
};
