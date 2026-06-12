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
  RotateCcw,
  Search,
  Square,
  Terminal,
  Trash2,
  UploadCloud,
  UserRoundCog,
  X,
} from 'lucide-react';
import {
  api,
  type AccountRole,
  type AccountStatus,
  type ApiAccount,
  type ApiFolder,
  type ApiFolderChannel,
  type FolderLog,
  type ImportItem,
  type ImportJob,
  type PortalUser,
} from './api';
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
type ChannelReviewFilter = 'all' | 'checked' | 'unchecked' | 'rejected';

const APP_PAGE_STORAGE_KEY = 'fnup.activePage';

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

function getActivePageStorageKey(portalUserKey: string) {
  return `${APP_PAGE_STORAGE_KEY}.${portalUserKey || 'anonymous'}`;
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

const folderUi = {
  channels: '\u041a\u0430\u043d\u0430\u043b\u044b',
  channel: '\u041a\u0430\u043d\u0430\u043b',
  subscribers: '\u041f\u043e\u0434\u043f\u0438\u0441\u0447\u0438\u043a\u0438',
  folder: '\u041f\u0430\u043f\u043a\u0430',
  addedAt: '\u0414\u0430\u0442\u0430 \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u0438\u044f',
  search: '\u041f\u043e\u0438\u0441\u043a \u043f\u043e \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044e \u0438\u043b\u0438 \u0441\u0441\u044b\u043b\u043a\u0435',
  showFolderChannels: '\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u043a\u0430\u043d\u0430\u043b\u044b \u043f\u0430\u043f\u043a\u0438',
  loadingChannels: '\u041a\u0430\u043d\u0430\u043b\u044b \u0437\u0430\u0433\u0440\u0443\u0436\u0430\u044e\u0442\u0441\u044f',
  noChannels: '\u041a\u0430\u043d\u0430\u043b\u044b \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b',
  loadChannelsFailed: '\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u043a\u0430\u043d\u0430\u043b\u044b',
  all: '\u0412\u0441\u0435',
  checked: '\u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043d\u044b\u0435',
  unchecked: '\u041d\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043d\u044b\u0435',
  rejected: '\u041d\u0435 \u043f\u043e\u0434\u0445\u043e\u0434\u044f\u0442',
  review: '\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430',
  approved: '\u041f\u0440\u043e\u0432\u0435\u0440\u0435\u043d',
  rejectedOne: '\u041d\u0435 \u043f\u043e\u0434\u0445\u043e\u0434\u0438\u0442',
  logsConsole: '\u041a\u043e\u043d\u0441\u043e\u043b\u044c \u043b\u043e\u0433\u043e\u0432',
  clearLogs: '\u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u043b\u043e\u0433\u0438',
  noLogs: '\u041b\u043e\u0433\u043e\u0432 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442',
  folders: '\u041f\u0430\u043f\u043a\u0438',
  listener: '\u0421\u043b\u0443\u0448\u0430\u0442\u0435\u043b\u044c \u043f\u0430\u043f\u043a\u0438',
  account: '\u0410\u043a\u043a\u0430\u0443\u043d\u0442',
  noAccounts: '\u041d\u0435\u0442 \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u043e\u0432',
  getFolders: '\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u043f\u0430\u043f\u043a\u0438',
  noFolderSelected: '\u041d\u0435 \u0432\u044b\u0431\u0440\u0430\u043d\u0430',
  noFolders: '\u041f\u0430\u043f\u043e\u043a \u043d\u0435\u0442',
  channelsCount: '\u043a\u0430\u043d\u0430\u043b\u043e\u0432',
  start: '\u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c',
  stop: '\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c',
  started: '\u0417\u0430\u043f\u0443\u0449\u0435\u043d\u043e',
  stopped: '\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e',
  stateFailed: '\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0441\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0435 \u0441\u043b\u0443\u0448\u0430\u0442\u0435\u043b\u044f',
  savedFoldersFailed: '\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043d\u044b\u0435 \u043f\u0430\u043f\u043a\u0438',
  refreshFoldersFailed: '\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u043f\u0430\u043f\u043a\u0438 \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u0430',
  toggleFailed: '\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0435\u0440\u0435\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0441\u043b\u0443\u0448\u0430\u0442\u0435\u043b\u044c',
  returnToUnchecked: '\u0412\u0435\u0440\u043d\u0443\u0442\u044c \u0432 \u043d\u0435\u043f\u0440\u043e\u0432\u0435\u0440\u0435\u043d\u043d\u044b\u0435',
  deleteChannels: '\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u043a\u0430\u043d\u0430\u043b\u044b',
  selectChannel: '\u0412\u044b\u0431\u0440\u0430\u0442\u044c \u043a\u0430\u043d\u0430\u043b',
  selected: '\u0432\u044b\u0431\u0440\u0430\u043d\u043e',
  deleteSelected: '\u0423\u0434\u0430\u043b\u0438\u0442\u044c',
  chooseChannels: '\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435',
  selectedFolderMissing: '\u0412\u044b\u0431\u0440\u0430\u043d\u043d\u0430\u044f \u043f\u0430\u043f\u043a\u0430 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442 \u043d\u0430 \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u0435. \u0421\u043f\u0438\u0441\u043e\u043a \u043f\u0430\u043f\u043e\u043a \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d.',
};

function getChannelInitials(title: string) {
  return (title || 'CH')
    .split(/\s|_/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'CH';
}

function ChannelAvatar({ src, title, size = 'normal' }: { src: string; title: string; size?: 'normal' | 'small' }) {
  const avatarUrl = api.mediaUrl(src);
  if (!avatarUrl) {
    return <span className={`channelAvatar channelAvatarFallback ${size}`}>{getChannelInitials(title)}</span>;
  }

  return <img className={`channelAvatar ${size}`} src={avatarUrl} alt="" loading="lazy" title={title} />;
}

function channelMatchesSearch(channel: ApiFolderChannel, normalizedSearch: string) {
  return (
    !normalizedSearch ||
    channel.title.toLowerCase().includes(normalizedSearch) ||
    channel.url.toLowerCase().includes(normalizedSearch) ||
    channel.username.toLowerCase().includes(normalizedSearch)
  );
}

function FolderChannelsTable({ channels, isLoading }: { channels: ApiFolderChannel[]; isLoading: boolean }) {
  const [expandedChannelId, setExpandedChannelId] = useState<string | null>(null);
  const [searchValue, setSearchValue] = useState('');

  const normalizedSearch = searchValue.trim().toLowerCase();
  const filteredChannels = useMemo(
    () => channels.filter((channel) => channelMatchesSearch(channel, normalizedSearch)),
    [channels, normalizedSearch],
  );

  return (
    <section className="folderChannelsPanel">
      <header className="panelHeader folderChannelsHeader">
        <div>
          <h2>{folderUi.channels}</h2>
        </div>
        <label className="channelSearch">
          <Search size={16} />
          <input value={searchValue} onChange={(event) => setSearchValue(event.target.value)} placeholder={folderUi.search} />
        </label>
      </header>
      <div className="animatedTableShell">
        <div className="animatedTableGradient top" />
        <div className="folderChannelsScroll">
          <table className="folderChannelsTable">
            <thead>
              <tr>
                <th>{folderUi.channel}</th>
                <th>{folderUi.subscribers}</th>
                <th>Avg views</th>
                <th>{folderUi.folder}</th>
                <th>{folderUi.addedAt}</th>
              </tr>
            </thead>
            <tbody>
              {filteredChannels.length ? (
                filteredChannels.map((channel, index) => {
                  const isExpanded = expandedChannelId === channel.id;

                  return (
                    <motion.tr className="folderChannelRow" data-index={index} initial={{ scale: 0.97, opacity: 0 }} whileInView={{ scale: 1, opacity: 1 }} viewport={{ amount: 0.42, once: false }} transition={{ duration: 0.2, delay: 0.04 }} key={channel.id}>
                      <td>
                        <div className="channelIdentity">
                          <ChannelAvatar src={channel.avatar_url} title={channel.title} />
                          <a href={channel.url} target="_blank" rel="noreferrer">
                            {channel.title}
                            <ExternalLink size={14} aria-hidden="true" />
                          </a>
                        </div>
                      </td>
                      <td className="metricCell">{formatMetric(channel.subscribers)}</td>
                      <td className="metricCell">{formatMetric(channel.avg_views)}</td>
                      <td>
                        <div className="folderSourceCell">
                          {channel.source_channels.length > 0 ? (
                            <>
                              <button className={`sourceToggle${isExpanded ? ' isOpen' : ''}`} type="button" onClick={() => setExpandedChannelId((value) => (value === channel.id ? null : channel.id))} aria-label={folderUi.showFolderChannels}>
                                <span>{formatChannelsCount(channel.source_channels.length)}</span>
                                <ChevronDown size={15} />
                              </button>
                              <AnimatePresence initial={false}>
                                {isExpanded && (
                                  <motion.div className="sourceChannelsList" initial={{ opacity: 0, y: -6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6, scale: 0.98 }} transition={{ duration: 0.16 }}>
                                    {channel.source_channels.map((source, sourceIndex) => (
                                      <motion.div className="sourceChannelItem" initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.16, delay: sourceIndex * 0.035 }} key={source.id}>
                                        <ChannelAvatar src={source.avatar_url} title={source.title} size="small" />
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
                      <td className="mutedText">{formatDateTime(channel.added_at)}</td>
                    </motion.tr>
                  );
                })
              ) : (
                <tr>
                  <td className="emptyCell" colSpan={5}>{isLoading ? folderUi.loadingChannels : folderUi.noChannels}</td>
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

function ChannelsPage() {
  const [channels, setChannels] = useState<ApiFolderChannel[]>([]);
  const [activeFilter, setActiveFilter] = useState<ChannelReviewFilter>('all');
  const [expandedChannelId, setExpandedChannelId] = useState<string | null>(null);
  const [searchValue, setSearchValue] = useState('');
  const [isLoadingChannels, setIsLoadingChannels] = useState(true);
  const [channelsError, setChannelsError] = useState('');
  const [deleteMode, setDeleteMode] = useState(false);
  const [selectedChannelIds, setSelectedChannelIds] = useState<number[]>([]);

  async function loadChannels() {
    setChannelsError('');
    setIsLoadingChannels(true);
    try {
      const payload = await api.listChannels();
      setChannels(payload.items);
    } catch (err) {
      setChannelsError(err instanceof Error ? err.message : folderUi.loadChannelsFailed);
    } finally {
      setIsLoadingChannels(false);
    }
  }

  useEffect(() => {
    void loadChannels();
  }, []);

  const counts = useMemo(
    () => ({
      all: channels.filter((channel) => channel.check_status !== 'rejected').length,
      checked: channels.filter((channel) => channel.check_status === 'checked').length,
      unchecked: channels.filter((channel) => channel.check_status === 'unchecked').length,
      rejected: channels.filter((channel) => channel.check_status === 'rejected').length,
    }),
    [channels],
  );

  const normalizedSearch = searchValue.trim().toLowerCase();
  const visibleChannels = useMemo(
    () =>
      channels.filter((channel) => {
        const matchesFilter = (activeFilter === 'all' && channel.check_status !== 'rejected') || (activeFilter !== 'all' && channel.check_status === activeFilter);
        return matchesFilter && channelMatchesSearch(channel, normalizedSearch);
      }),
    [activeFilter, channels, normalizedSearch],
  );
  const visibleChannelIds = useMemo(() => visibleChannels.map((channel) => channel.channel_id), [visibleChannels]);
  const allVisibleSelected = visibleChannelIds.length > 0 && visibleChannelIds.every((channelId) => selectedChannelIds.includes(channelId));

  function toggleSelectedChannel(channelId: number) {
    setSelectedChannelIds((items) => (items.includes(channelId) ? items.filter((item) => item !== channelId) : [...items, channelId]));
  }

  function toggleVisibleChannels() {
    setSelectedChannelIds((items) => {
      if (allVisibleSelected) {
        return items.filter((channelId) => !visibleChannelIds.includes(channelId));
      }
      return Array.from(new Set([...items, ...visibleChannelIds]));
    });
  }

  async function approveChannel(channelId: number) {
    await api.approveChannel(channelId);
    setChannels((items) => items.map((channel) => (channel.channel_id === channelId ? { ...channel, check_status: 'checked' } : channel)));
  }

  async function rejectChannel(channelId: number) {
    await api.rejectChannel(channelId);
    setChannels((items) => items.map((channel) => (channel.channel_id === channelId ? { ...channel, check_status: 'rejected' } : channel)));
  }

  async function resetChannel(channelId: number) {
    await api.resetChannel(channelId);
    setChannels((items) => items.map((channel) => (channel.channel_id === channelId ? { ...channel, check_status: 'unchecked' } : channel)));
  }

  async function toggleDeleteMode() {
    if (deleteMode && selectedChannelIds.length) {
      await api.deleteChannels(selectedChannelIds);
      setChannels((items) => items.filter((channel) => !selectedChannelIds.includes(channel.channel_id)));
      setSelectedChannelIds([]);
      setDeleteMode(false);
      return;
    }
    setDeleteMode((value) => !value);
    setSelectedChannelIds([]);
  }

  const filters: Array<{ id: ChannelReviewFilter; label: string; count: number }> = [
    { id: 'all', label: folderUi.all, count: counts.all },
    { id: 'checked', label: folderUi.checked, count: counts.checked },
    { id: 'unchecked', label: folderUi.unchecked, count: counts.unchecked },
    { id: 'rejected', label: folderUi.rejected, count: counts.rejected },
  ];

  return (
    <>
      <header className="topBar"><div><h1>{folderUi.channels}</h1></div></header>
      <section className="folderChannelsPanel channelsReviewPanel">
        <header className="panelHeader folderChannelsHeader">
          <div><h2>{folderUi.channels}</h2></div>
          <div className="channelHeaderTools">
            <label className="channelSearch"><Search size={16} /><input value={searchValue} onChange={(event) => setSearchValue(event.target.value)} placeholder={folderUi.search} /></label>
            <button className={`inlineIconButton deleteModeButton${deleteMode ? ' isActive' : ''}`} type="button" onClick={() => void toggleDeleteMode()} title={folderUi.deleteChannels} aria-label={folderUi.deleteChannels}>
              <Trash2 size={16} />
              {deleteMode && <span>{selectedChannelIds.length > 0 ? `${folderUi.deleteSelected} ${selectedChannelIds.length}` : folderUi.chooseChannels}</span>}
            </button>
          </div>
        </header>
        <div className="channelFilterBar">
          {filters.map((filter) => (
            <button className={`channelFilterButton${activeFilter === filter.id ? ' isActive' : ''}`} type="button" onClick={() => setActiveFilter(filter.id)} key={filter.id}>{filter.label} <span>({filter.count})</span></button>
          ))}
        </div>
        {channelsError && <div className="folderInlineError">{channelsError}</div>}
        <div className="animatedTableShell">
          <div className="animatedTableGradient top" />
          <div className="folderChannelsScroll channelsReviewScroll">
            <table className="folderChannelsTable channelReviewTable">
              <thead><tr><th><span className="channelHeaderLabel"><span className="channelSelectSlot">{deleteMode && <button className={`channelSelectBox headerSelectBox${allVisibleSelected ? ' isSelected' : ''}`} type="button" onClick={toggleVisibleChannels} title={folderUi.selectChannel} aria-label={folderUi.selectChannel} disabled={!visibleChannelIds.length}>{allVisibleSelected && <CheckCircle2 size={14} />}</button>}</span>{folderUi.channel}</span></th><th>{folderUi.subscribers}</th><th>Avg views</th><th>{folderUi.folder}</th><th>{folderUi.addedAt}</th><th>{folderUi.review}</th></tr></thead>
              <tbody>
                {visibleChannels.length ? visibleChannels.map((channel, index) => {
                  const isExpanded = expandedChannelId === channel.id;
                  const isSelected = selectedChannelIds.includes(channel.channel_id);
                  return (
                    <motion.tr className="folderChannelRow" data-index={index} initial={{ scale: 0.97, opacity: 0 }} whileInView={{ scale: 1, opacity: 1 }} viewport={{ amount: 0.42, once: false }} transition={{ duration: 0.2, delay: 0.04 }} key={channel.id}>
                      <td>
                        <div className="channelIdentity">
                          <span className="channelSelectSlot">
                            {deleteMode && (
                              <button className={`channelSelectBox${isSelected ? ' isSelected' : ''}`} type="button" onClick={() => toggleSelectedChannel(channel.channel_id)} title={folderUi.selectChannel} aria-label={folderUi.selectChannel}>
                                {isSelected && <CheckCircle2 size={14} />}
                              </button>
                            )}
                          </span>
                          <ChannelAvatar src={channel.avatar_url} title={channel.title} />
                          <a href={channel.url} target="_blank" rel="noreferrer">{channel.title}<ExternalLink size={14} aria-hidden="true" /></a>
                        </div>
                      </td>
                      <td className="metricCell">{formatMetric(channel.subscribers)}</td>
                      <td className="metricCell">{formatMetric(channel.avg_views)}</td>
                      <td><div className="folderSourceCell">{channel.source_channels.length > 0 ? <><button className={`sourceToggle${isExpanded ? ' isOpen' : ''}`} type="button" onClick={() => setExpandedChannelId((value) => (value === channel.id ? null : channel.id))} aria-label={folderUi.showFolderChannels}><span>{formatChannelsCount(channel.source_channels.length)}</span><ChevronDown size={15} /></button><AnimatePresence initial={false}>{isExpanded && <motion.div className="sourceChannelsList" initial={{ opacity: 0, y: -6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6, scale: 0.98 }} transition={{ duration: 0.16 }}>{channel.source_channels.map((source, sourceIndex) => <motion.div className="sourceChannelItem" initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.16, delay: sourceIndex * 0.035 }} key={source.id}><ChannelAvatar src={source.avatar_url} title={source.title} size="small" /><span>{source.title}</span></motion.div>)}</motion.div>}</AnimatePresence></> : <span className="folderSourceDash">&mdash;</span>}</div></td>
                      <td className="mutedText">{formatDateTime(channel.added_at)}</td>
                      <td>
                        {channel.check_status === 'checked' ? (
                          <div className="channelReviewActions"><span className="channelReviewState checked" title={folderUi.approved} aria-label={folderUi.approved}><CheckCircle2 size={17} /></span><button className="inlineIconButton reset" type="button" onClick={() => void resetChannel(channel.channel_id)} title={folderUi.returnToUnchecked} aria-label={folderUi.returnToUnchecked}><RotateCcw size={16} /></button></div>
                        ) : channel.check_status === 'rejected' ? (
                          <div className="channelReviewActions"><span className="channelReviewState rejected" title={folderUi.rejectedOne} aria-label={folderUi.rejectedOne}><X size={17} /></span><button className="inlineIconButton reset" type="button" onClick={() => void resetChannel(channel.channel_id)} title={folderUi.returnToUnchecked} aria-label={folderUi.returnToUnchecked}><RotateCcw size={16} /></button></div>
                        ) : (
                          <div className="channelReviewActions"><button className="inlineIconButton approve" type="button" onClick={() => void approveChannel(channel.channel_id)} title={folderUi.approved} aria-label={folderUi.approved}><CheckCircle2 size={16} /></button><button className="inlineIconButton reject" type="button" onClick={() => void rejectChannel(channel.channel_id)} title={folderUi.rejectedOne} aria-label={folderUi.rejectedOne}><X size={16} /></button></div>
                        )}
                      </td>
                    </motion.tr>
                  );
                }) : <tr><td className="emptyCell" colSpan={6}>{isLoadingChannels ? folderUi.loadingChannels : folderUi.noChannels}</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="animatedTableGradient bottom" />
        </div>
      </section>
    </>
  );
}

function FolderLogsConsole({ logs, onClear, isClearing }: { logs: FolderLog[]; onClear: () => void; isClearing: boolean }) {
  const logLabels: Record<string, string> = { info: 'INFO', success: 'OK', warn: 'WARN', system: 'SYSTEM', scan: 'SCAN' };
  const bodyRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const body = bodyRef.current;
    if (body) body.scrollTop = body.scrollHeight;
  }, [logs]);
  return (
    <section className="folderLogsPanel">
      <header className="folderLogsHeader">
        <div><Terminal size={17} /><h2>{folderUi.logsConsole}</h2></div>
        <button className="ghostButton clearLogsButton" type="button" onClick={onClear} disabled={!logs.length || isClearing} title={folderUi.clearLogs} aria-label={folderUi.clearLogs}>{isClearing ? <Loader2 className="spinIcon" size={15} /> : <Trash2 size={15} />}</button>
      </header>
      <div className="folderLogsBody" ref={bodyRef}>
        {logs.length ? logs.map((log) => <div className="folderLogRow" key={log.id}><time>{formatLogTime(log.timestamp)}</time><span className={`folderLogType ${log.type}`}>{logLabels[log.type] || log.type.toUpperCase()}</span><p>{log.message}</p></div>) : <div className="folderLogEmpty">{folderUi.noLogs}</div>}
      </div>
    </section>
  );
}

function FoldersPage({ accounts, portalUser }: { accounts: ApiAccount[]; portalUser: PortalUser | null }) {
  void portalUser;
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [folders, setFolders] = useState<ApiFolder[]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState('');
  const [status, setStatus] = useState<ListenerStatus>('idle');
  const [isFetchingFolders, setIsFetchingFolders] = useState(false);
  const [isTogglingListener, setIsTogglingListener] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<'account' | 'folder' | null>(null);
  const [folderError, setFolderError] = useState('');
  const [folderChannels, setFolderChannels] = useState<ApiFolderChannel[]>([]);
  const [isLoadingChannels, setIsLoadingChannels] = useState(false);
  const [folderLogs, setFolderLogs] = useState<FolderLog[]>([]);
  const [isClearingLogs, setIsClearingLogs] = useState(false);

  async function loadFolderLogs() { const payload = await api.listFolderLogs(); setFolderLogs(payload.items); }
  async function loadFolderChannels(accountId: number, folderId: string) {
    if (!accountId || !folderId) { setFolderChannels([]); return; }
    setIsLoadingChannels(true);
    try { const payload = await api.listFolderChannels(accountId, folderId); setFolderChannels(payload.items); } finally { setIsLoadingChannels(false); }
  }
  async function loadListenerStatus(accountId: number, folderId: string) {
    if (!accountId || !folderId) { setStatus('idle'); return; }
    const payload = await api.getFolderListenerStatus(accountId, folderId);
    setStatus(payload.status === 'running' ? 'running' : 'idle');
  }
  async function loadRuntimeState(accountId: number, folderId: string) {
    setFolderError('');
    try { await Promise.all([loadListenerStatus(accountId, folderId), loadFolderChannels(accountId, folderId), loadFolderLogs()]); } catch (err) { setFolderError(err instanceof Error ? err.message : folderUi.stateFailed); }
  }

  useEffect(() => {
    if (!accounts.length) return;
    api.getActiveFolderListener()
      .then((payload) => {
        if (payload.status === 'running' && payload.account_id && payload.folder_id) {
          setSelectedAccountId(String(payload.account_id));
          setSelectedFolderId(String(payload.folder_id));
          setStatus('running');
        }
      })
      .catch(() => undefined);
  }, [accounts.length]);

  useEffect(() => { if (!selectedAccountId && accounts.length) setSelectedAccountId(String(accounts[0].account_id)); }, [accounts, selectedAccountId]);
  useEffect(() => {
    const accountId = Number(selectedAccountId);
    if (!accountId) { setFolders([]); setSelectedFolderId(''); setFolderChannels([]); setStatus('idle'); return; }
    setFolderError('');
    api.listAccountFolders(accountId).then((payload) => { setFolders(payload.items); setSelectedFolderId((current) => (payload.items.some((item) => item.id === current) ? current : payload.items[0]?.id || '')); }).catch((err: unknown) => { setFolders([]); setSelectedFolderId(''); setFolderChannels([]); setStatus('idle'); setFolderError(err instanceof Error ? err.message : folderUi.savedFoldersFailed); });
  }, [selectedAccountId]);
  useEffect(() => {
    const accountId = Number(selectedAccountId);
    if (!accountId || !selectedFolderId) { setFolderChannels([]); setStatus('idle'); void loadFolderLogs().catch(() => undefined); return; }
    void loadRuntimeState(accountId, selectedFolderId);
  }, [selectedAccountId, selectedFolderId]);
  useEffect(() => {
    if (status !== 'running') return undefined;
    const timer = window.setInterval(() => { const accountId = Number(selectedAccountId); if (accountId && selectedFolderId) void Promise.all([loadListenerStatus(accountId, selectedFolderId), loadFolderChannels(accountId, selectedFolderId), loadFolderLogs()]).catch(() => undefined); }, 3500);
    return () => window.clearInterval(timer);
  }, [selectedAccountId, selectedFolderId, status]);

  async function fetchFolders() {
    const accountId = Number(selectedAccountId);
    if (!accountId) return;
    setOpenDropdown(null); setFolderError(''); setIsFetchingFolders(true);
    try {
      const payload = await api.refreshAccountFolders(accountId);
      const nextFolderId = payload.items.some((item) => item.id === selectedFolderId) ? selectedFolderId : payload.items[0]?.id || '';
      setFolders(payload.items);
      setSelectedFolderId(nextFolderId);
      if (nextFolderId) {
        await api.syncAccountFolder(accountId, nextFolderId);
        await loadFolderChannels(accountId, nextFolderId);
      } else {
        setFolderChannels([]);
      }
    } catch (err) { setFolders([]); setSelectedFolderId(''); setFolderChannels([]); setStatus('idle'); setFolderError(err instanceof Error ? err.message : folderUi.refreshFoldersFailed); } finally { setIsFetchingFolders(false); }
  }
  async function toggleListening() {
    const accountId = Number(selectedAccountId);
    if (!accountId || !selectedFolderId) return;
    setOpenDropdown(null); setFolderError(''); setIsTogglingListener(true);
    try {
      if (status !== 'running') {
        const foldersPayload = await api.refreshAccountFolders(accountId);
        setFolders(foldersPayload.items);
        if (!foldersPayload.items.some((folderItem) => folderItem.id === selectedFolderId)) {
          setSelectedFolderId('');
          setStatus('idle');
          setFolderChannels([]);
          setFolderError(folderUi.selectedFolderMissing);
          await loadFolderLogs();
          return;
        }
      }
      const payload = status === 'running' ? await api.stopFolderListener(accountId, selectedFolderId) : await api.startFolderListener(accountId, selectedFolderId);
      setStatus(payload.status === 'running' ? 'running' : 'idle');
      await Promise.all([loadFolderChannels(accountId, selectedFolderId), loadFolderLogs()]);
    } catch (err) { setFolderError(err instanceof Error ? err.message : folderUi.toggleFailed); } finally { setIsTogglingListener(false); }
  }
  async function clearFolderLogs() { setIsClearingLogs(true); try { await api.clearFolderLogs(); setFolderLogs([]); } finally { setIsClearingLogs(false); } }

  const selectedAccount = accounts.find((account) => String(account.account_id) === selectedAccountId);
  const selectedFolder = folders.find((folderItem) => folderItem.id === selectedFolderId);

  return (
    <>
      <header className="topBar"><div><h1>{folderUi.folders}</h1></div></header>
      <section className="folderControlPanel">
        <header className="panelHeader folderPanelHeader"><div><h2>{folderUi.listener}</h2></div></header>
        <div className="folderControls">
          <div className="fieldBlock"><span>{folderUi.account}</span><div className={`customSelect accountSelect${openDropdown === 'account' ? ' isOpen' : ''}`}><button className="customSelectButton" type="button" onClick={() => setOpenDropdown((value) => (value === 'account' ? null : 'account'))} disabled={!accounts.length || status === 'running'}>{selectedAccount ? <span className="selectAccountValue"><Avatar item={selectedAccount} /><span><strong>{getDisplayName(selectedAccount)}</strong><em>{selectedAccount.username || '@unknown'}</em></span></span> : <span className="selectPlaceholder">{folderUi.noAccounts}</span>}<ChevronDown size={16} /></button>{openDropdown === 'account' && <div className="customSelectMenu">{accounts.length ? accounts.map((account) => <button className={`customSelectOption accountOption${String(account.account_id) === selectedAccountId ? ' isSelected' : ''}`} type="button" onClick={() => { setSelectedAccountId(String(account.account_id)); setFolderError(''); setStatus('idle'); setOpenDropdown(null); }} key={account.account_id}><Avatar item={account} /><span><strong>{getDisplayName(account)}</strong><em>{account.username || '@unknown'}</em></span></button>) : <span className="customSelectEmpty">{folderUi.noAccounts}</span>}</div>}</div></div>
          <button className="iconButton folderFetchButton" type="button" onClick={fetchFolders} disabled={!selectedAccountId || isFetchingFolders || status === 'running'} title={folderUi.getFolders} aria-label={folderUi.getFolders}>{isFetchingFolders ? <Loader2 className="spinIcon" size={17} /> : <RefreshCw size={17} />}</button>
          <div className="fieldBlock"><span>{folderUi.folder}</span><div className={`customSelect${openDropdown === 'folder' ? ' isOpen' : ''}`}><button className="customSelectButton" type="button" onClick={() => setOpenDropdown((value) => (value === 'folder' ? null : 'folder'))} disabled={status === 'running'}><span className="selectFolderValue">{selectedFolder?.title || (folders.length ? folderUi.noFolderSelected : folderUi.noFolders)}</span><ChevronDown size={16} /></button>{openDropdown === 'folder' && <div className="customSelectMenu">{folders.length ? folders.map((folderItem) => <button className={`customSelectOption folderOption${folderItem.id === selectedFolderId ? ' isSelected' : ''}`} type="button" onClick={() => { setSelectedFolderId(folderItem.id); setOpenDropdown(null); }} key={folderItem.id}><FolderOpen size={17} /><span><strong>{folderItem.title}</strong><em>{folderItem.channels} {folderUi.channelsCount}</em></span></button>) : <span className="customSelectEmpty">{folderUi.noFolders}</span>}</div>}</div></div>
          <div className="folderRunBar"><button className="primaryButton" type="button" onClick={() => void toggleListening()} disabled={!selectedAccountId || !selectedFolderId || isTogglingListener}>{isTogglingListener ? <Loader2 className="spinIcon" size={16} /> : status === 'running' ? <Square size={16} /> : <Play size={16} />}{status === 'running' ? folderUi.stop : folderUi.start}</button><span className={`listenerDot ${status}`} title={status === 'running' ? folderUi.started : folderUi.stopped} aria-label={status === 'running' ? folderUi.started : folderUi.stopped} /></div>
        </div>
        {folderError && <div className="folderInlineError">{folderError}</div>}
      </section>
      <section className="folderSnapshotGrid"><article className="folderSnapshot wide"><span><UserRoundCog size={18} /></span><div><p>{folderUi.account}</p><strong>{selectedAccount ? getDisplayName(selectedAccount) : '?'}</strong></div></article><article className="folderSnapshot"><span><FolderOpen size={18} /></span><div><p>{folderUi.folder}</p><strong>{selectedFolder?.title || '?'}</strong></div></article><article className="folderSnapshot"><span><RadioTower size={18} /></span><div><p>{folderUi.channels}</p><strong>{folderChannels.length || selectedFolder?.channels || '?'}</strong></div></article></section>
      <FolderChannelsTable channels={folderChannels} isLoading={isLoadingChannels} />
      <FolderLogsConsole logs={folderLogs} onClear={() => void clearFolderLogs()} isClearing={isClearingLogs} />
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
        {activePage === 'channels' && <ChannelsPage />}
        {activePage === 'chat' && (
          <section className="placeholderPanel">
            <h1>Chat</h1>
          </section>
        )}
      </section>
      {isModalOpen && <ImportModal onClose={() => setIsModalOpen(false)} onAccountsChanged={loadAccounts} />}
    </main>
  );
}
