import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  CheckCircle2,
  ChevronDown,
  Eye,
  EyeOff,
  ExternalLink,
  Folder,
  FolderOpen,
  HardDriveUpload,
  Hash,
  Loader2,
  LockKeyhole,
  MessageCircle,
  Phone,
  Play,
  RadioTower,
  RefreshCw,
  Search,
  Square,
  Terminal,
  Trash2,
  UploadCloud,
  UserRoundCog,
  X,
} from 'lucide-react';
import { api, type AccountRole, type AccountStatus, type ApiAccount, type ApiFolder, type ImportItem, type ImportJob, type PortalUser } from './api';
import { VerticalDock } from './components/VerticalDock';

const validityLabels: Record<string, string> = {
  valid: 'Валиден',
  warning: 'Нужна проверка',
  invalid: 'Ошибка',
};

const importStatusLabels: Record<string, string> = {
  processing: 'Обработка',
  done: 'Загружен',
  checked: 'Проверен',
  saved: 'Сохранен',
  failed: 'Ошибка',
};

const roleClassNames: Record<AccountRole, string> = {
  Каналы: 'channels',
  Чаты: 'chats',
  Био: 'bio',
  Папка: 'folder',
};

type AppPage = 'accounts' | 'chat' | 'folder' | 'channels';
type ListenerStatus = 'idle' | 'running';

const APP_PAGE_STORAGE_KEY = 'fnup.activePage';
const FOLDER_LOGS_STORAGE_KEY = 'fnup.folderLogs';

type FolderLogType = 'info' | 'success' | 'warn' | 'system' | 'scan';

type FolderLogEntry = {
  id: string;
  timestamp: string;
  type: FolderLogType;
  message: string;
};

type MockFolderChannel = {
  id: string;
  title: string;
  url: string;
  avatarUrl: string;
  subscribers: number;
  avgViews: number;
  addedAt: string;
  sourceChannels: Array<{
    id: string;
    title: string;
    avatarUrl: string;
  }>;
};

const mockFolderChannels: MockFolderChannel[] = [
  {
    id: 'ch_aurora_tape',
    title: 'Aurora Tape',
    url: 'https://t.me/aurora_tape',
    avatarUrl: 'https://picsum.photos/seed/aurora-tape/96/96',
    subscribers: 18420,
    avgViews: 4210,
    addedAt: '2026-06-11T12:48:00Z',
    sourceChannels: [
      { id: 'src_cryptoline', title: 'Cryptoline Daily', avatarUrl: 'https://picsum.photos/seed/cryptoline/72/72' },
      { id: 'src_alpha', title: 'Alpha Signal Room', avatarUrl: 'https://picsum.photos/seed/alpha-signal/72/72' },
      { id: 'src_vectormarket', title: 'Vector Market', avatarUrl: 'https://picsum.photos/seed/vector-market/72/72' },
    ],
  },
  {
    id: 'ch_northdesk',
    title: 'Northdesk Briefs',
    url: 'https://t.me/northdesk_briefs',
    avatarUrl: 'https://picsum.photos/seed/northdesk-briefs/96/96',
    subscribers: 73200,
    avgViews: 12840,
    addedAt: '2026-06-11T11:19:00Z',
    sourceChannels: [
      { id: 'src_launch', title: 'Launch Scanner', avatarUrl: 'https://picsum.photos/seed/launch-scanner/72/72' },
      { id: 'src_delta', title: 'Delta Feed', avatarUrl: 'https://picsum.photos/seed/delta-feed/72/72' },
    ],
  },
  {
    id: 'ch_signalforge',
    title: 'Signal Forge',
    url: 'https://t.me/signal_forge',
    avatarUrl: 'https://picsum.photos/seed/signal-forge/96/96',
    subscribers: 29640,
    avgViews: 6730,
    addedAt: '2026-06-10T22:06:00Z',
    sourceChannels: [
      { id: 'src_cryptoline', title: 'Cryptoline Daily', avatarUrl: 'https://picsum.photos/seed/cryptoline/72/72' },
      { id: 'src_radar', title: 'Radar Watch', avatarUrl: 'https://picsum.photos/seed/radar-watch/72/72' },
      { id: 'src_mono', title: 'Mono Ledger', avatarUrl: 'https://picsum.photos/seed/mono-ledger/72/72' },
      { id: 'src_pulse', title: 'Pulse Queue', avatarUrl: 'https://picsum.photos/seed/pulse-queue/72/72' },
    ],
  },
  {
    id: 'ch_echochain',
    title: 'Echochain Research',
    url: 'https://t.me/echochain_research',
    avatarUrl: 'https://picsum.photos/seed/echochain-research/96/96',
    subscribers: 118900,
    avgViews: 24100,
    addedAt: '2026-06-10T19:37:00Z',
    sourceChannels: [],
  },
  {
    id: 'ch_quantdock',
    title: 'Quant Dock',
    url: 'https://t.me/quant_dock',
    avatarUrl: 'https://picsum.photos/seed/quant-dock/96/96',
    subscribers: 45280,
    avgViews: 9520,
    addedAt: '2026-06-09T17:12:00Z',
    sourceChannels: [
      { id: 'src_delta', title: 'Delta Feed', avatarUrl: 'https://picsum.photos/seed/delta-feed/72/72' },
      { id: 'src_vectormarket', title: 'Vector Market', avatarUrl: 'https://picsum.photos/seed/vector-market/72/72' },
    ],
  },
  {
    id: 'ch_blackterminal',
    title: 'Black Terminal',
    url: 'https://t.me/black_terminal',
    avatarUrl: 'https://picsum.photos/seed/black-terminal/96/96',
    subscribers: 9130,
    avgViews: 3140,
    addedAt: '2026-06-09T14:25:00Z',
    sourceChannels: [
      { id: 'src_launch', title: 'Launch Scanner', avatarUrl: 'https://picsum.photos/seed/launch-scanner/72/72' },
      { id: 'src_mono', title: 'Mono Ledger', avatarUrl: 'https://picsum.photos/seed/mono-ledger/72/72' },
      { id: 'src_pulse', title: 'Pulse Queue', avatarUrl: 'https://picsum.photos/seed/pulse-queue/72/72' },
    ],
  },
  {
    id: 'ch_meridiannode',
    title: 'Meridian Node',
    url: 'https://t.me/meridian_node',
    avatarUrl: 'https://picsum.photos/seed/meridian-node/96/96',
    subscribers: 56110,
    avgViews: 11080,
    addedAt: '2026-06-08T21:03:00Z',
    sourceChannels: [
      { id: 'src_radar', title: 'Radar Watch', avatarUrl: 'https://picsum.photos/seed/radar-watch/72/72' },
      { id: 'src_cryptoline', title: 'Cryptoline Daily', avatarUrl: 'https://picsum.photos/seed/cryptoline/72/72' },
    ],
  },
  {
    id: 'ch_coldindex',
    title: 'Cold Index',
    url: 'https://t.me/cold_index',
    avatarUrl: 'https://picsum.photos/seed/cold-index/96/96',
    subscribers: 34780,
    avgViews: 8060,
    addedAt: '2026-06-08T16:44:00Z',
    sourceChannels: [],
  },
  {
    id: 'ch_circuitbrief',
    title: 'Circuit Brief',
    url: 'https://t.me/circuit_brief',
    avatarUrl: 'https://picsum.photos/seed/circuit-brief/96/96',
    subscribers: 140300,
    avgViews: 31290,
    addedAt: '2026-06-07T18:31:00Z',
    sourceChannels: [
      { id: 'src_delta', title: 'Delta Feed', avatarUrl: 'https://picsum.photos/seed/delta-feed/72/72' },
      { id: 'src_alpha', title: 'Alpha Signal Room', avatarUrl: 'https://picsum.photos/seed/alpha-signal/72/72' },
      { id: 'src_launch', title: 'Launch Scanner', avatarUrl: 'https://picsum.photos/seed/launch-scanner/72/72' },
    ],
  },
];

const initialFolderLogs: FolderLogEntry[] = [
  {
    id: 'log_seed_1',
    timestamp: '2026-06-11T12:48:10Z',
    type: 'system',
    message: 'Консоль слушателя папки инициализирована',
  },
  {
    id: 'log_seed_2',
    timestamp: '2026-06-11T12:49:02Z',
    type: 'info',
    message: 'Обнаружена папка (3 канала) в канале Aurora Tape',
  },
  {
    id: 'log_seed_3',
    timestamp: '2026-06-11T12:49:08Z',
    type: 'scan',
    message: 'Сканирую 3 канала из найденной папки',
  },
  {
    id: 'log_seed_4',
    timestamp: '2026-06-11T12:49:17Z',
    type: 'success',
    message: '3 канала добавлено в таблицу',
  },
  {
    id: 'log_seed_5',
    timestamp: '2026-06-11T12:51:40Z',
    type: 'warn',
    message: 'Повторная ссылка на уже обработанную папку пропущена',
  },
];

function createFolderLog(type: FolderLogType, message: string): FolderLogEntry {
  return {
    id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
    timestamp: new Date().toISOString(),
    type,
    message,
  };
}

function getPortalStorageUser(currentUser: PortalUser | null, accounts: ApiAccount[] = []) {
  if (currentUser?.portal_user_id) {
    return currentUser.portal_user_id;
  }
  if (currentUser?.portal_username) {
    return currentUser.portal_username;
  }

  const accountWithUserId = accounts.find((account) => account.portal_user_id);
  if (accountWithUserId?.portal_user_id) {
    return accountWithUserId.portal_user_id;
  }

  const accountWithUsername = accounts.find((account) => account.portal_username);
  return accountWithUsername?.portal_username || 'anonymous';
}

function getFolderLogsStorageKey(portalUserKey: string) {
  return `${FOLDER_LOGS_STORAGE_KEY}.${portalUserKey || 'anonymous'}`;
}

function getActivePageStorageKey(portalUserKey: string) {
  return `${APP_PAGE_STORAGE_KEY}.${portalUserKey || 'anonymous'}`;
}

function getStoredFolderLogs(storageKey: string) {
  if (typeof window === 'undefined') {
    return initialFolderLogs;
  }

  const value = window.localStorage.getItem(storageKey);
  if (!value) {
    return initialFolderLogs;
  }

  try {
    const parsed = JSON.parse(value) as FolderLogEntry[];
    return Array.isArray(parsed) ? parsed : initialFolderLogs;
  } catch {
    return initialFolderLogs;
  }
}

function maskPhone(phone: string) {
  if (!phone) {
    return 'не прочитан';
  }
  return phone.replace(/(\+\d{1,3})\s?(\d{2,4}).*(\d{2})$/, '$1 $2 *** ** $3');
}

function getDisplayName(account: Pick<ApiAccount | ImportItem, 'display_name' | 'username' | 'user_id'>) {
  return account.display_name || account.username || (account.user_id ? `user_${account.user_id}` : 'Аккаунт');
}

function getInitials(account: { display_name?: string; username?: string; filename?: string; user_id?: number }) {
  const source = account.display_name || account.username || account.filename || String(account.user_id || 'TG');
  return source
    .replace('@', '')
    .split(/\s|_/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'TG';
}

function normalizeGeo(geo: string) {
  const match = (geo || '').trim().match(/[a-z]{2}/i);
  return match ? match[0].toLowerCase() : '';
}

function formatDateTime(value: string) {
  if (!value) {
    return 'не проверялся';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function formatLogTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date);
}

function formatMetric(value: number) {
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: value >= 1000 ? 1 : 0,
    notation: value >= 10000 ? 'compact' : 'standard',
  }).format(value);
}

function formatChannelsCount(value: number) {
  const tail = value % 10;
  const tailHundred = value % 100;
  if (tail === 1 && tailHundred !== 11) {
    return `${value} канал`;
  }
  if (tail >= 2 && tail <= 4 && (tailHundred < 12 || tailHundred > 14)) {
    return `${value} канала`;
  }
  return `${value} каналов`;
}

function PhoneCell({ phone }: { phone: string }) {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <div className="phoneReveal">
      <button
        className="inlineIconButton"
        type="button"
        onClick={() => setIsVisible((value) => !value)}
        title={isVisible ? 'Скрыть номер' : 'Показать номер'}
        aria-label={isVisible ? 'Скрыть номер' : 'Показать номер'}
      >
        {isVisible ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
      <span>{isVisible ? phone || 'не прочитан' : maskPhone(phone)}</span>
    </div>
  );
}

function Avatar({ item }: { item: ApiAccount | ImportItem }) {
  const avatarUrl = item.avatar_url ? api.mediaUrl(item.avatar_url) : '';

  if (avatarUrl) {
    return <img className="avatar imageAvatar" src={avatarUrl} alt="" />;
  }

  return <div className="avatar">{getInitials(item)}</div>;
}

function ValidityBadge({ status }: { status: AccountStatus }) {
  const normalized = status === 'valid' || status === 'invalid' ? status : 'warning';

  return (
    <span className={`validityBadge ${normalized}`}>
      <i />
      {validityLabels[normalized] || validityLabels.warning}
    </span>
  );
}

function GeoFlag({ geo }: { geo: string }) {
  const code = normalizeGeo(geo);
  if (!code) {
    return <span className="flagIcon flagFallback" title="Гео не определено" aria-label="Гео не определено" />;
  }
  return (
    <span className="flagIcon" title={geo.toUpperCase()} aria-label={geo.toUpperCase()}>
      <img
        src={`https://flagcdn.com/w40/${code}.png`}
        srcSet={`https://flagcdn.com/w80/${code}.png 2x`}
        alt=""
        loading="lazy"
        onError={(event) => {
          event.currentTarget.style.display = 'none';
          event.currentTarget.parentElement?.classList.add('flagFallback');
        }}
      />
    </span>
  );
}

function AccountRow({ account, onCheck, checkingId }: { account: ApiAccount; onCheck: (id: number) => void; checkingId: number | null }) {
  const roles = account.roles || [];

  return (
    <tr>
      <td>
        <div className="accountIdentity">
          <Avatar item={account} />
          <div>
            <strong>{getDisplayName(account)}</strong>
            <span>{account.username || '@unknown'}</span>
          </div>
        </div>
      </td>
      <td className="phoneCell">
        <PhoneCell phone={account.phone} />
      </td>
      <td>
        <GeoFlag geo={account.geo} />
      </td>
      <td>
        <div className="roleList">
          {roles.length ? (
            roles.map((role) => (
              <span className={`roleBadge ${roleClassNames[role]}`} key={role}>
                {role}
              </span>
            ))
          ) : (
            <span className="mutedText">—</span>
          )}
        </div>
      </td>
      <td>
        <ValidityBadge status={account.account_status} />
      </td>
      <td className="mutedText">{formatDateTime(account.checked_at)}</td>
      <td>
        <button
          className="iconButton"
          type="button"
          title="Проверить аккаунт"
          aria-label="Проверить аккаунт"
          onClick={() => onCheck(account.account_id)}
          disabled={checkingId === account.account_id}
        >
          {checkingId === account.account_id ? <Loader2 className="spinIcon" size={17} /> : <CheckCircle2 size={17} />}
        </button>
      </td>
    </tr>
  );
}

function ImportRow({ item }: { item: ImportItem }) {
  const normalizedStatus = item.status === 'failed' ? 'invalid' : item.status === 'checked' || item.status === 'saved' ? 'valid' : 'warning';
  const statusMessage = item.message || importStatusLabels[item.status] || item.status;

  return (
    <tr>
      <td>
        <div className="accountIdentity">
          <Avatar item={item} />
          <div>
            <strong>{getDisplayName(item)}</strong>
            <span>{item.username || item.filename}</span>
          </div>
        </div>
      </td>
      <td className="phoneCell">
        <PhoneCell phone={item.phone} />
      </td>
      <td>
        <GeoFlag geo={item.geo} />
      </td>
      <td>
        <span className={`validityBadge importStatus ${normalizedStatus}`} data-tooltip={statusMessage} tabIndex={0}>
          <i />
          {importStatusLabels[item.status] || item.status}
        </span>
      </td>
    </tr>
  );
}

function ImportModal({ onClose, onAccountsChanged }: { onClose: () => void; onAccountsChanged: () => Promise<void> }) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [jobIds, setJobIds] = useState<string[]>([]);
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [items, setItems] = useState<ImportItem[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [phoneInput, setPhoneInput] = useState('');
  const [phoneCode, setPhoneCode] = useState('');
  const [phonePassword, setPhonePassword] = useState('');
  const [activePhoneFlow, setActivePhoneFlow] = useState<{ flowId: string; jobId: string; phone: string; step: 'code' | 'password' } | null>(null);
  const [isPhoneBusy, setIsPhoneBusy] = useState(false);
  const [error, setError] = useState('');

  async function refreshJobs(nextJobIds = jobIds) {
    const uniqueIds = Array.from(new Set(nextJobIds.filter(Boolean)));
    if (!uniqueIds.length) {
      setJobs([]);
      setItems([]);
      return [];
    }

    const payloads = await Promise.all(
      uniqueIds.map(async (jobId) => {
        const [jobPayload, itemsPayload] = await Promise.all([api.getImportJob(jobId), api.getImportItems(jobId)]);
        return { job: jobPayload, items: itemsPayload.items };
      }),
    );

    setJobs(payloads.map((payload) => payload.job));
    setItems(payloads.flatMap((payload) => payload.items));
    return payloads.map((payload) => payload.job);
  }

  useEffect(() => {
    if (!jobIds.length || jobs.every((item) => item.finished_at)) {
      return;
    }

    const timer = window.setInterval(() => {
      refreshJobs(jobIds).catch((err: unknown) => setError(err instanceof Error ? err.message : 'Ошибка обновления импорта'));
    }, 1200);

    return () => window.clearInterval(timer);
  }, [jobIds, jobs]);

  function appendJob(jobId: string) {
    const nextJobIds = Array.from(new Set([...jobIds, jobId]));
    setJobIds(nextJobIds);
    return nextJobIds;
  }

  async function startUpload(nextFiles = files) {
    if (!nextFiles.length) {
      setError('Выберите .session файлы');
      return;
    }

    setError('');
    setIsUploading(true);
    try {
      const payload = await api.uploadSessions(nextFiles);
      await refreshJobs(appendJob(payload.job_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка импорта');
    } finally {
      setIsUploading(false);
    }
  }

  async function checkImportedAccounts() {
    if (!jobIds.length) {
      return;
    }
    setError('');
    setIsChecking(true);
    try {
      await Promise.all(jobIds.map((jobId) => api.checkImportJob(jobId)));
      await refreshJobs(jobIds);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка проверки');
    } finally {
      setIsChecking(false);
    }
  }

  async function saveImportedAccounts() {
    if (!jobIds.length) {
      return;
    }
    setError('');
    setIsSaving(true);
    try {
      await Promise.all(jobIds.map((jobId) => api.saveImportJob(jobId)));
      await refreshJobs(jobIds);
      await onAccountsChanged();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка сохранения');
    } finally {
      setIsSaving(false);
    }
  }

  function handleFiles(fileList: FileList | null) {
    const nextFiles = Array.from(fileList || []);
    setFiles(nextFiles);
    if (nextFiles.length) {
      void startUpload(nextFiles);
    }
  }

  async function startPhone(phone: string) {
    setIsPhoneBusy(true);
    setError('');
    setPhoneCode('');
    setPhonePassword('');
    try {
      const payload = await api.startPhoneImport(phone);
      const nextJobIds = appendJob(payload.job_id);
      await refreshJobs(nextJobIds);
      if (!payload.flow_id || payload.next_step === 'done') {
        return;
      }
      setActivePhoneFlow({ flowId: payload.flow_id, jobId: payload.job_id, phone, step: payload.next_step });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка авторизации по номеру');
    } finally {
      setIsPhoneBusy(false);
    }
  }

  async function startPhoneAuth() {
    const phone = phoneInput.trim();
    if (!phone) {
      setError('Введите номер телефона');
      return;
    }
    await startPhone(phone);
  }

  async function submitPhoneCode() {
    if (!activePhoneFlow) {
      return;
    }
    const nextJobIds = Array.from(new Set([...jobIds, activePhoneFlow.jobId]));
    setIsPhoneBusy(true);
    setError('');
    try {
      const payload = await api.submitPhoneCode(activePhoneFlow.flowId, phoneCode);
      await refreshJobs(nextJobIds);
      if (payload.next_step === 'password') {
        setActivePhoneFlow({ ...activePhoneFlow, step: 'password' });
        return;
      }
      setActivePhoneFlow(null);
      setPhoneInput('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка подтверждения кода');
    } finally {
      setIsPhoneBusy(false);
    }
  }

  async function submitPhonePassword() {
    if (!activePhoneFlow) {
      return;
    }
    const nextJobIds = Array.from(new Set([...jobIds, activePhoneFlow.jobId]));
    setIsPhoneBusy(true);
    setError('');
    try {
      await api.submitPhonePassword(activePhoneFlow.flowId, phonePassword);
      await refreshJobs(nextJobIds);
      setActivePhoneFlow(null);
      setPhoneInput('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка 2FA');
    } finally {
      setIsPhoneBusy(false);
    }
  }

  async function cancelPhoneFlow() {
    if (!activePhoneFlow) {
      return;
    }
    const nextJobIds = Array.from(new Set([...jobIds, activePhoneFlow.jobId]));
    setIsPhoneBusy(true);
    try {
      await api.cancelPhoneImport(activePhoneFlow.flowId);
      await refreshJobs(nextJobIds);
      setActivePhoneFlow(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка отмены авторизации');
    } finally {
      setIsPhoneBusy(false);
    }
  }

  const canCheck = Boolean(jobIds.length) && items.some((item) => item.status === 'done');
  const canSave = Boolean(jobIds.length) && items.some((item) => item.status === 'checked' || item.status === 'done');
  const totalSuccess = jobs.reduce((sum, item) => sum + item.success, 0);
  const totalFailed = jobs.reduce((sum, item) => sum + item.failed, 0);
  const jobStatus = jobs.length > 1 ? `${jobs.length} jobs` : jobs[0]?.status;

  return (
    <div className="modalBackdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="importModal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="importTitle"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span className="modalKicker">Telethon session import</span>
            <h2 id="importTitle">Импорт аккаунта</h2>
          </div>
          <button className="iconButton" type="button" onClick={onClose} aria-label="Закрыть">
            <X size={18} />
          </button>
        </header>
        <div className="importMethods">
          <label
            className="dropzone methodCard"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              handleFiles(event.dataTransfer.files);
            }}
          >
            <input ref={inputRef} type="file" multiple accept=".session" onChange={(event) => handleFiles(event.target.files)} />
            <div className="sessionImportCore">
              {isUploading ? <Loader2 className="spinIcon" size={32} /> : <UploadCloud size={32} />}
              <strong>{files.length ? `${files.length} файл(ов) выбрано` : 'Импорт .session'}</strong>
            </div>
            <span>Перетащите файл или нажмите для выбора</span>
          </label>

          <section className="phoneMethod methodCard">
            <div className="phoneMethodHeader">
              <Phone size={28} />
              <strong>Авторизация по номеру</strong>
            </div>
            {!activePhoneFlow ? (
              <>
                <input
                  className="phoneNumberInput"
                  value={phoneInput}
                  onChange={(event) => setPhoneInput(event.target.value)}
                  placeholder="+79999999999"
                />
                <button className="ghostButton accent" type="button" onClick={startPhoneAuth} disabled={isPhoneBusy}>
                  {isPhoneBusy ? <Loader2 className="spinIcon" size={17} /> : <Phone size={17} />}
                  Получить код
                </button>
              </>
            ) : activePhoneFlow.step === 'code' ? (
              <>
                <p className="mutedText">Код отправлен на {activePhoneFlow.phone}</p>
                <div className="phoneStepRow">
                  <Hash size={17} />
                  <input value={phoneCode} onChange={(event) => setPhoneCode(event.target.value)} placeholder="Код Telegram" />
                </div>
                <div className="phoneStepActions">
                  <button className="ghostButton" type="button" onClick={cancelPhoneFlow} disabled={isPhoneBusy}>Отмена</button>
                  <button className="primaryButton" type="button" onClick={submitPhoneCode} disabled={isPhoneBusy}>
                    {isPhoneBusy ? <Loader2 className="spinIcon" size={17} /> : <CheckCircle2 size={17} />}
                    Подтвердить
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="mutedText">Введите пароль 2FA для {activePhoneFlow.phone}</p>
                <div className="phoneStepRow">
                  <LockKeyhole size={17} />
                  <input value={phonePassword} onChange={(event) => setPhonePassword(event.target.value)} placeholder="Пароль 2FA" type="password" />
                </div>
                <div className="phoneStepActions">
                  <button className="ghostButton" type="button" onClick={cancelPhoneFlow} disabled={isPhoneBusy}>Отмена</button>
                  <button className="primaryButton" type="button" onClick={submitPhonePassword} disabled={isPhoneBusy}>
                    {isPhoneBusy ? <Loader2 className="spinIcon" size={17} /> : <CheckCircle2 size={17} />}
                    Завершить
                  </button>
                </div>
              </>
            )}
          </section>
        </div>

        {error && <div className="errorNotice">{error}</div>}

        <section className="importPreview">
          <header>
            <div>
              <h3>Импортируемые аккаунты</h3>
              {jobs.length > 0 && <p className="mutedText">Job: {jobStatus}, успешно: {totalSuccess}, ошибок: {totalFailed}</p>}
            </div>
            <button className="ghostButton accent" type="button" onClick={checkImportedAccounts} disabled={!canCheck || isChecking}>
              {isChecking ? <Loader2 className="spinIcon" size={17} /> : <CheckCircle2 size={17} />}
              Проверить аккаунты
            </button>
          </header>
          <div className="tableWrap mini">
            <table>
              <thead>
                <tr>
                  <th>Аккаунт</th>
                  <th>Номер</th>
                  <th>Гео</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {items.length ? (
                  items.map((item) => <ImportRow item={item} key={item.item_id} />)
                ) : (
                  <tr>
                    <td className="emptyCell" colSpan={4}>Импортированных аккаунтов пока нет</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <footer>
          <button className="ghostButton" type="button" onClick={onClose}>
            Отмена
          </button>
          <button className="primaryButton" type="button" onClick={saveImportedAccounts} disabled={!canSave || isSaving}>
            {isSaving ? <Loader2 className="spinIcon" size={17} /> : <HardDriveUpload size={17} />}
            Импортировать
          </button>
        </footer>
      </section>
    </div>
  );
}

function ChannelAvatar({ src, title, size = 'normal' }: { src: string; title: string; size?: 'normal' | 'small' }) {
  return <img className={`channelAvatar ${size}`} src={src} alt="" loading="lazy" title={title} />;
}

function FolderChannelsTable() {
  const [expandedChannelId, setExpandedChannelId] = useState<string | null>(null);
  const [searchValue, setSearchValue] = useState('');

  const normalizedSearch = searchValue.trim().toLowerCase();
  const filteredChannels = useMemo(
    () =>
      mockFolderChannels.filter((channel) => {
        return (
          !normalizedSearch ||
          channel.title.toLowerCase().includes(normalizedSearch) ||
          channel.url.toLowerCase().includes(normalizedSearch)
        );
      }),
    [normalizedSearch],
  );

  return (
    <section className="folderChannelsPanel">
      <header className="panelHeader folderChannelsHeader">
        <div>
          <h2>Каналы</h2>
        </div>
        <label className="channelSearch">
          <Search size={16} />
          <input
            value={searchValue}
            onChange={(event) => setSearchValue(event.target.value)}
            placeholder="Поиск по названию или ссылке"
          />
        </label>
      </header>
      <div className="animatedTableShell">
        <div className="animatedTableGradient top" />
        <div className="folderChannelsScroll">
          <table className="folderChannelsTable">
            <thead>
              <tr>
                <th>Канал</th>
                <th>Подписчики</th>
                <th>Avg views</th>
                <th>Папка</th>
                <th>Дата добавления</th>
              </tr>
            </thead>
            <tbody>
              {filteredChannels.length ? (
                filteredChannels.map((channel, index) => {
                const isExpanded = expandedChannelId === channel.id;

                return (
                  <motion.tr
                    className="folderChannelRow"
                    data-index={index}
                    initial={{ scale: 0.97, opacity: 0 }}
                    whileInView={{ scale: 1, opacity: 1 }}
                    viewport={{ amount: 0.42, once: false }}
                    transition={{ duration: 0.2, delay: 0.04 }}
                    key={channel.id}
                  >
                    <td>
                      <div className="channelIdentity">
                        <ChannelAvatar src={channel.avatarUrl} title={channel.title} />
                        <a href={channel.url} target="_blank" rel="noreferrer">
                          {channel.title}
                          <ExternalLink size={14} aria-hidden="true" />
                        </a>
                      </div>
                    </td>
                    <td className="metricCell">{formatMetric(channel.subscribers)}</td>
                    <td className="metricCell">{formatMetric(channel.avgViews)}</td>
                    <td>
                      <div className="folderSourceCell">
                        {channel.sourceChannels.length > 0 ? (
                          <>
                            <button
                              className={`sourceToggle${isExpanded ? ' isOpen' : ''}`}
                              type="button"
                              onClick={() => setExpandedChannelId((value) => (value === channel.id ? null : channel.id))}
                              aria-label="Показать каналы папки"
                            >
                              <span>{formatChannelsCount(channel.sourceChannels.length)}</span>
                              <ChevronDown size={15} />
                            </button>
                            <AnimatePresence initial={false}>
                              {isExpanded && (
                                <motion.div
                                  className="sourceChannelsList"
                                  initial={{ opacity: 0, y: -6, scale: 0.98 }}
                                  animate={{ opacity: 1, y: 0, scale: 1 }}
                                  exit={{ opacity: 0, y: -6, scale: 0.98 }}
                                  transition={{ duration: 0.16 }}
                                >
                                  {channel.sourceChannels.map((source, sourceIndex) => (
                                    <motion.div
                                      className="sourceChannelItem"
                                      initial={{ opacity: 0, x: -6 }}
                                      animate={{ opacity: 1, x: 0 }}
                                      transition={{ duration: 0.16, delay: sourceIndex * 0.035 }}
                                      key={source.id}
                                    >
                                      <ChannelAvatar src={source.avatarUrl} title={source.title} size="small" />
                                      <span>{source.title}</span>
                                    </motion.div>
                                  ))}
                                </motion.div>
                              )}
                            </AnimatePresence>
                          </>
                        ) : (
                          <span className="folderSourceDash">&mdash;</span>
                        )}
                      </div>
                    </td>
                    <td className="mutedText">{formatDateTime(channel.addedAt)}</td>
                  </motion.tr>
                );
              })
              ) : (
                <tr>
                  <td className="emptyCell" colSpan={5}>Каналы не найдены</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="animatedTableGradient bottom" />
      </div>
    </section>
  );
}

function FolderLogsConsole({ logs, onClear }: { logs: FolderLogEntry[]; onClear: () => void }) {
  const logLabels: Record<FolderLogType, string> = {
    info: 'INFO',
    success: 'OK',
    warn: 'WARN',
    system: 'SYSTEM',
    scan: 'SCAN',
  };

  return (
    <section className="folderLogsPanel">
      <header className="folderLogsHeader">
        <div>
          <Terminal size={17} />
          <h2>Консоль логов</h2>
        </div>
        <button
          className="ghostButton clearLogsButton"
          type="button"
          onClick={onClear}
          disabled={!logs.length}
          title="Очистить логи"
          aria-label="Очистить логи"
        >
          <Trash2 size={15} />
        </button>
      </header>
      <div className="folderLogsBody">
        {logs.length ? (
          logs.map((log) => (
            <div className="folderLogRow" key={log.id}>
              <time>{formatLogTime(log.timestamp)}</time>
              <span className={`folderLogType ${log.type}`}>{logLabels[log.type]}</span>
              <p>{log.message}</p>
            </div>
          ))
        ) : (
          <div className="folderLogEmpty">Логов пока нет</div>
        )}
      </div>
    </section>
  );
}

function FoldersPage({ accounts, portalUser }: { accounts: ApiAccount[]; portalUser: PortalUser | null }) {
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [folders, setFolders] = useState<ApiFolder[]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState('');
  const [status, setStatus] = useState<ListenerStatus>('idle');
  const [isFetchingFolders, setIsFetchingFolders] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<'account' | 'folder' | null>(null);
  const [folderError, setFolderError] = useState('');
  const portalStorageUser = getPortalStorageUser(portalUser, accounts);
  const folderLogsStorageKey = getFolderLogsStorageKey(portalStorageUser);
  const activeLogsKeyRef = useRef(folderLogsStorageKey);
  const [folderLogs, setFolderLogs] = useState<FolderLogEntry[]>(() => getStoredFolderLogs(folderLogsStorageKey));

  useEffect(() => {
    if (activeLogsKeyRef.current !== folderLogsStorageKey) {
      activeLogsKeyRef.current = folderLogsStorageKey;
      setFolderLogs(getStoredFolderLogs(folderLogsStorageKey));
    }
  }, [folderLogsStorageKey]);

  useEffect(() => {
    if (activeLogsKeyRef.current === folderLogsStorageKey) {
      window.localStorage.setItem(folderLogsStorageKey, JSON.stringify(folderLogs));
    }
  }, [folderLogs, folderLogsStorageKey]);

  function appendFolderLog(type: FolderLogType, message: string) {
    setFolderLogs((items) => [...items, createFolderLog(type, message)].slice(-160));
  }

  useEffect(() => {
    if (!selectedAccountId && accounts.length) {
      setSelectedAccountId(String(accounts[0].account_id));
    }
  }, [accounts, selectedAccountId]);

  useEffect(() => {
    const accountId = Number(selectedAccountId);
    if (!accountId) {
      setFolders([]);
      setSelectedFolderId('');
      return;
    }

    setFolderError('');
    api.listAccountFolders(accountId)
      .then((payload) => {
        setFolders(payload.items);
        setSelectedFolderId(payload.items[0]?.id || '');
      })
      .catch((err: unknown) => {
        setFolders([]);
        setSelectedFolderId('');
        setFolderError(err instanceof Error ? err.message : 'Не удалось загрузить сохраненные папки');
      });
  }, [selectedAccountId]);

  async function fetchFolders() {
    const accountId = Number(selectedAccountId);
    if (!accountId) {
      return;
    }

    setOpenDropdown(null);
    setFolderError('');
    setIsFetchingFolders(true);
    appendFolderLog('scan', 'Получаю список папок аккаунта');
    try {
      const payload = await api.refreshAccountFolders(accountId);
      setFolders(payload.items);
      setSelectedFolderId(payload.items[0]?.id || '');
      appendFolderLog(payload.items.length ? 'success' : 'warn', payload.items.length ? `Получено папок: ${payload.items.length}` : 'На аккаунте папки не найдены');
    } catch (err) {
      setFolders([]);
      setSelectedFolderId('');
      setFolderError(err instanceof Error ? err.message : 'Не удалось получить папки аккаунта');
      appendFolderLog('warn', 'Не удалось получить папки аккаунта');
    } finally {
      setIsFetchingFolders(false);
    }
  }

  function toggleListening() {
    if (!selectedAccountId || !selectedFolderId) {
      return;
    }
    setOpenDropdown(null);
    const nextStatus = status === 'running' ? 'idle' : 'running';
    setStatus(nextStatus);
    appendFolderLog(nextStatus === 'running' ? 'system' : 'warn', nextStatus === 'running' ? 'Парсер запущен' : 'Парсер остановлен');
  }

  const selectedAccount = accounts.find((account) => String(account.account_id) === selectedAccountId);
  const selectedFolder = folders.find((folderItem) => folderItem.id === selectedFolderId);

  return (
    <>
      <header className="topBar">
        <div>
          <h1>Папки</h1>
        </div>
      </header>

      <section className="folderControlPanel">
        <header className="panelHeader folderPanelHeader">
          <div>
            <h2>Слушатель папки</h2>
          </div>
        </header>

        <div className="folderControls">
          <div className="fieldBlock">
            <span>Аккаунт</span>
            <div className={`customSelect accountSelect${openDropdown === 'account' ? ' isOpen' : ''}`}>
              <button
                className="customSelectButton"
                type="button"
                onClick={() => setOpenDropdown((value) => (value === 'account' ? null : 'account'))}
                disabled={!accounts.length}
              >
                {selectedAccount ? (
                  <span className="selectAccountValue">
                    <Avatar item={selectedAccount} />
                    <span>
                      <strong>{getDisplayName(selectedAccount)}</strong>
                      <em>{selectedAccount.username || '@unknown'}</em>
                    </span>
                  </span>
                ) : (
                  <span className="selectPlaceholder">Нет аккаунтов</span>
                )}
                <ChevronDown size={16} />
              </button>
              {openDropdown === 'account' && (
                <div className="customSelectMenu">
                {accounts.length ? (
                  accounts.map((account) => (
                    <button
                      className={`customSelectOption accountOption${String(account.account_id) === selectedAccountId ? ' isSelected' : ''}`}
                      type="button"
                      onClick={() => {
                        setSelectedAccountId(String(account.account_id));
                        setFolderError('');
                        setStatus('idle');
                        setOpenDropdown(null);
                      }}
                      key={account.account_id}
                    >
                      <Avatar item={account} />
                      <span>
                        <strong>{getDisplayName(account)}</strong>
                        <em>{account.username || '@unknown'}</em>
                      </span>
                    </button>
                  ))
                ) : (
                  <span className="customSelectEmpty">Нет аккаунтов</span>
                )}
                </div>
              )}
            </div>
          </div>

          <button
            className="iconButton folderFetchButton"
            type="button"
            onClick={fetchFolders}
            disabled={!selectedAccountId || isFetchingFolders}
            title="Получить папки"
            aria-label="Получить папки"
          >
            {isFetchingFolders ? <Loader2 className="spinIcon" size={17} /> : <RefreshCw size={17} />}
          </button>

          <div className="fieldBlock">
            <span>Папка</span>
            <div className={`customSelect${openDropdown === 'folder' ? ' isOpen' : ''}`}>
              <button
                className="customSelectButton"
                type="button"
                onClick={() => setOpenDropdown((value) => (value === 'folder' ? null : 'folder'))}
              >
                <span className="selectFolderValue">{selectedFolder?.title || (folders.length ? 'Не выбрана' : 'Папок нет')}</span>
                <ChevronDown size={16} />
              </button>
              {openDropdown === 'folder' && (
                <div className="customSelectMenu">
                {folders.length ? (
                  folders.map((folderItem) => (
                    <button
                      className={`customSelectOption folderOption${folderItem.id === selectedFolderId ? ' isSelected' : ''}`}
                      type="button"
                      onClick={() => {
                        setSelectedFolderId(folderItem.id);
                        setOpenDropdown(null);
                      }}
                      key={folderItem.id}
                    >
                      <FolderOpen size={17} />
                      <span>
                        <strong>{folderItem.title}</strong>
                        <em>{folderItem.channels} каналов</em>
                      </span>
                    </button>
                  ))
                ) : (
                  <span className="customSelectEmpty">Папок нет</span>
                )}
                </div>
              )}
            </div>
          </div>

          <div className="folderRunBar">
            <button className="primaryButton" type="button" onClick={toggleListening} disabled={!selectedAccountId || !selectedFolderId}>
              {status === 'running' ? <Square size={16} /> : <Play size={16} />}
              {status === 'running' ? 'Остановить' : 'Запустить'}
            </button>
            <span
              className={`listenerDot ${status}`}
              title={status === 'running' ? 'Запущено' : 'Остановлено'}
              aria-label={status === 'running' ? 'Запущено' : 'Остановлено'}
            />
          </div>
        </div>

        {folderError && <div className="folderInlineError">{folderError}</div>}
      </section>

      <section className="folderSnapshotGrid">
        <article className="folderSnapshot wide">
          <span>
            <UserRoundCog size={18} />
          </span>
          <div>
            <p>Аккаунт</p>
            <strong>{selectedAccount ? getDisplayName(selectedAccount) : '—'}</strong>
          </div>
        </article>
        <article className="folderSnapshot">
          <span>
            <FolderOpen size={18} />
          </span>
          <div>
            <p>Папка</p>
            <strong>{selectedFolder?.title || '—'}</strong>
          </div>
        </article>
        <article className="folderSnapshot">
          <span>
            <RadioTower size={18} />
          </span>
          <div>
            <p>Каналов</p>
            <strong>{selectedFolder?.channels ?? '—'}</strong>
          </div>
        </article>
      </section>
      <FolderChannelsTable />
      <FolderLogsConsole logs={folderLogs} onClear={() => setFolderLogs([])} />
    </>
  );
}

function getStoredPage(storageKey = APP_PAGE_STORAGE_KEY): AppPage {
  if (typeof window === 'undefined') {
    return 'accounts';
  }
  const value = window.localStorage.getItem(storageKey);
  return value === 'accounts' || value === 'chat' || value === 'folder' || value === 'channels' ? value : 'accounts';
}

export function App() {
  const [portalUser, setPortalUser] = useState<PortalUser | null>(null);
  const [accounts, setAccounts] = useState<ApiAccount[]>([]);
  const portalStorageUser = getPortalStorageUser(portalUser, accounts);
  const activePageStorageKey = getActivePageStorageKey(portalStorageUser);
  const activePageKeyRef = useRef(activePageStorageKey);
  const [activePage, setActivePage] = useState<AppPage>(() => getStoredPage(activePageStorageKey));
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [checkingId, setCheckingId] = useState<number | null>(null);
  const [error, setError] = useState('');

  async function loadAccounts() {
    setError('');
    try {
      const [userPayload, accountsPayload] = await Promise.all([api.getCurrentUser(), api.listAccounts()]);
      setPortalUser(userPayload);
      setAccounts(accountsPayload.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить аккаунты');
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadAccounts();
  }, []);

  useEffect(() => {
    if (activePageKeyRef.current !== activePageStorageKey) {
      activePageKeyRef.current = activePageStorageKey;
      setActivePage(getStoredPage(activePageStorageKey));
    }
  }, [activePageStorageKey]);

  useEffect(() => {
    if (activePageKeyRef.current === activePageStorageKey) {
      window.localStorage.setItem(activePageStorageKey, activePage);
    }
  }, [activePage, activePageStorageKey]);

  async function checkAccount(accountId: number) {
    setCheckingId(accountId);
    setError('');
    try {
      await api.checkAccounts([accountId]);
      await loadAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось проверить аккаунт');
    } finally {
      setCheckingId(null);
    }
  }

  const stats = useMemo(
    () => [
      { label: 'Аккаунтов', value: accounts.length, icon: UserRoundCog },
      { label: 'Валидных', value: accounts.filter((account) => account.account_status === 'valid').length, icon: CheckCircle2 },
    ],
    [accounts],
  );

  const navItems = [
    { icon: <UserRoundCog size={22} />, label: 'Аккаунты', active: activePage === 'accounts', onClick: () => setActivePage('accounts') },
    { icon: <MessageCircle size={22} />, label: 'Chat', active: activePage === 'chat', onClick: () => setActivePage('chat') },
    { icon: <Folder size={22} />, label: 'Folder', active: activePage === 'folder', onClick: () => setActivePage('folder') },
    { icon: <RadioTower size={22} />, label: 'Каналы', active: activePage === 'channels', onClick: () => setActivePage('channels') },
  ];

  return (
    <main className="appShell">
      <VerticalDock items={navItems} />
      <section className="pageSurface">
        <div className="ambientGlow one" />
        <div className="ambientGlow two" />
        {activePage !== 'accounts' && error && <div className="errorNotice">{error}</div>}
        {activePage === 'accounts' && (
          <>
            <header className="topBar">
              <div>
                <h1>Менеджер аккаунтов</h1>
              </div>
              <div className="topActions">
                <button className="primaryButton" type="button" onClick={() => setIsModalOpen(true)}>
                  <UploadCloud size={17} />
                  Импорт аккаунта
                </button>
              </div>
            </header>

            {error && <div className="errorNotice">{error}</div>}

            <section className="statsGrid compactStats">
              {stats.map((stat) => {
                const Icon = stat.icon;

                return (
                  <article className="statCard" key={stat.label}>
                    <span>
                      <Icon size={20} />
                    </span>
                    <div>
                      <strong>{stat.value}</strong>
                      <p>{stat.label}</p>
                    </div>
                  </article>
                );
              })}
            </section>

            <section className="accountsPanel">
              <header className="panelHeader">
                <div>
                  <h2>Таблица аккаунтов</h2>
                </div>
              </header>
              <div className="tableWrap">
                <table>
                  <thead>
                    <tr>
                      <th>Аватар / ник</th>
                      <th>Номер</th>
                      <th>Гео</th>
                      <th>Роли</th>
                      <th>Валидность</th>
                      <th>Проверка</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {isLoading ? (
                      <tr>
                        <td className="emptyCell" colSpan={7}>Загрузка аккаунтов...</td>
                      </tr>
                    ) : accounts.length ? (
                      accounts.map((account) => (
                        <AccountRow account={account} checkingId={checkingId} onCheck={checkAccount} key={account.account_id} />
                      ))
                    ) : (
                      <tr>
                        <td className="emptyCell" colSpan={7}>Аккаунтов пока нет</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
        {activePage === 'folder' && <FoldersPage accounts={accounts} portalUser={portalUser} />}
        {(activePage === 'chat' || activePage === 'channels') && (
          <section className="placeholderPanel">
            <h1>{activePage === 'chat' ? 'Chat' : 'Каналы'}</h1>
          </section>
        )}
      </section>
      {isModalOpen && <ImportModal onClose={() => setIsModalOpen(false)} onAccountsChanged={loadAccounts} />}
    </main>
  );
}
