import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  Check,
  ChevronDown,
  FolderOpen,
  Loader2,
  Plus,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import {
  api,
  type ApiChannelTable,
  type ApiFolderChannel,
  type ApiFolderCollection,
  type ApiFolderCollectionItem,
  type FolderCollectionRole,
} from '../api';

const collectionUi = {
  title: 'Сбор папок',
  subtitle: 'Собирайте состав папок, контакты админов и роли каналов',
  create: 'Создать папку',
  newFolder: 'Новая папка',
  addChannel: 'Добавить канал',
  channel: 'Канал',
  admin: 'Админ',
  role: 'Роль',
  folders: 'Папки',
  subscribers: 'Подписчики',
  avgViews: 'Avg Views',
  member: 'Участник',
  sponsor: 'Спонсор',
  channelPlaceholder: 'https://t.me/channel',
  adminPlaceholder: '@username',
  removeChannel: 'Убрать канал',
  deleteRow: 'Удалить строку',
  deleteFolder: 'Удалить папку',
  confirmDelete: 'Удалить?',
  cancel: 'Отмена',
  loading: 'Загружаем подборки',
  emptyTitle: 'Пока нет ни одной папки',
  emptyText: 'Нажмите на плюс, чтобы создать первую подборку каналов',
  noIntersections: 'Пересечений пока нет',
  loadFailed: 'Не удалось загрузить подборки',
  saveFailed: 'Не удалось сохранить изменения',
  deleteFailed: 'Не удалось удалить',
  noRows: 'Каналы в эту папку ещё не добавлены',
  noTables: 'Нет доступных таблиц каналов',
  myTable: 'Моя таблица',
  selectTable: 'Выбрать таблицу каналов',
};

function formatMetric(value: number) {
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: value >= 1000 ? 1 : 0,
    notation: value >= 10000 ? 'compact' : 'standard',
  }).format(value);
}

function formatChannelsCount(value: number) {
  const tail = value % 10;
  const tailHundred = value % 100;
  if (tail === 1 && tailHundred !== 11) return `${value} канал`;
  if (tail >= 2 && tail <= 4 && (tailHundred < 12 || tailHundred > 14)) return `${value} канала`;
  return `${value} каналов`;
}

function getChannelInitials(title: string) {
  return (title || 'CH')
    .split(/\s|_/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'CH';
}

function CollectionChannelAvatar({
  src,
  title,
  small = false,
}: {
  src: string;
  title: string;
  small?: boolean;
}) {
  const avatarUrl = api.mediaUrl(src);
  if (!avatarUrl) {
    return (
      <span className={`collectionChannelAvatar fallback${small ? ' small' : ''}`}>
        {getChannelInitials(title)}
      </span>
    );
  }
  return <img className={`collectionChannelAvatar${small ? ' small' : ''}`} src={avatarUrl} alt="" loading="lazy" />;
}

function normalizeTelegramRef(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/^www\./, '')
    .replace(/^telegram\.me\//, 't.me/')
    .replace(/^t\.me\//, '')
    .replace(/^@/, '')
    .split(/[/?#]/)[0];
}

function findChannelByRef(channels: ApiFolderChannel[], value: string) {
  const normalized = normalizeTelegramRef(value);
  if (!normalized) return null;
  return channels.find((channel) => (
    channel.check_status !== 'rejected'
    && (
      channel.username.trim().toLowerCase().replace(/^@/, '') === normalized
      || normalizeTelegramRef(channel.url) === normalized
    )
  )) || null;
}

function TableSelector({
  tables,
  selectedTable,
  isOpen,
  onToggle,
  onSelect,
}: {
  tables: ApiChannelTable[];
  selectedTable: ApiChannelTable | null;
  isOpen: boolean;
  onToggle: () => void;
  onSelect: (tableId: number) => void;
}) {
  if (!selectedTable) return null;
  if (tables.length === 1) {
    return (
      <span className="channelTableStatic collectionTableStatic">
        <Users size={16} />
        {selectedTable.is_owner ? collectionUi.myTable : selectedTable.title}
      </span>
    );
  }
  return (
    <div className={`channelTableSelect collectionTableSelect${isOpen ? ' isOpen' : ''}`}>
      <button className="channelTableButton" type="button" onClick={onToggle} aria-label={collectionUi.selectTable}>
        <Users size={16} />
        <span>{selectedTable.is_owner ? collectionUi.myTable : selectedTable.title}</span>
        <ChevronDown size={15} />
      </button>
      {isOpen && (
        <div className="channelTableMenu">
          {tables.map((table) => (
            <button
              className={`channelTableOption${table.id === selectedTable.id ? ' isSelected' : ''}`}
              type="button"
              onClick={() => onSelect(table.id)}
              key={table.id}
            >
              <strong>{table.is_owner ? collectionUi.myTable : table.title}</strong>
              <em>@{table.owner_portal_username || table.owner_portal_user_id || 'owner'}</em>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="collectionLoading" aria-label={collectionUi.loading}>
      {[0, 1].map((index) => (
        <div className="collectionSkeleton" style={{ animationDelay: `${index * 100}ms` }} key={index}>
          <span />
          <i />
          <i />
        </div>
      ))}
    </div>
  );
}

type OpenItemMenu = {
  type: 'role' | 'sources';
  itemId: number;
} | null;

export function FolderCollectionPage() {
  const [tables, setTables] = useState<ApiChannelTable[]>([]);
  const [selectedTableId, setSelectedTableId] = useState<number | null>(null);
  const [collections, setCollections] = useState<ApiFolderCollection[]>([]);
  const [channels, setChannels] = useState<ApiFolderChannel[]>([]);
  const [expandedCollectionIds, setExpandedCollectionIds] = useState<number[]>([]);
  const [openItemMenu, setOpenItemMenu] = useState<OpenItemMenu>(null);
  const [isTableMenuOpen, setIsTableMenuOpen] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [savingItemIds, setSavingItemIds] = useState<number[]>([]);
  const [error, setError] = useState('');

  const selectedTable = tables.find((table) => table.id === selectedTableId) || null;
  const channelById = useMemo(
    () => new Map(channels.map((channel) => [channel.channel_id, channel])),
    [channels],
  );

  useEffect(() => {
    api.listChannelTables()
      .then((payload) => {
        setTables(payload.items);
        setSelectedTableId(payload.items[0]?.id || null);
        if (!payload.items.length) setIsLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : collectionUi.loadFailed);
        setIsLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!selectedTableId) return;
    setIsLoading(true);
    setError('');
    setOpenItemMenu(null);
    setDeleteConfirmId(null);
    Promise.all([
      api.listChannels(selectedTableId),
      api.listFolderCollections(selectedTableId),
    ])
      .then(([channelPayload, collectionPayload]) => {
        setChannels(channelPayload.items);
        setCollections(collectionPayload.items);
        setExpandedCollectionIds(collectionPayload.items.map((collection) => collection.id));
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : collectionUi.loadFailed);
      })
      .finally(() => setIsLoading(false));
  }, [selectedTableId]);

  function replaceCollectionItem(
    collectionId: number,
    itemId: number,
    replacement: ApiFolderCollectionItem,
  ) {
    setCollections((items) => items.map((collection) => (
      collection.id === collectionId
        ? {
            ...collection,
            items: collection.items.map((item) => (item.id === itemId ? replacement : item)),
          }
        : collection
    )));
  }

  function patchCollectionItem(
    collectionId: number,
    itemId: number,
    patch: Partial<ApiFolderCollectionItem>,
  ) {
    setCollections((items) => items.map((collection) => (
      collection.id === collectionId
        ? {
            ...collection,
            items: collection.items.map((item) => (
              item.id === itemId ? { ...item, ...patch } : item
            )),
          }
        : collection
    )));
  }

  async function persistItem(
    collectionId: number,
    item: ApiFolderCollectionItem,
    patch: Partial<ApiFolderCollectionItem>,
  ) {
    const next = { ...item, ...patch };
    patchCollectionItem(collectionId, item.id, patch);
    setSavingItemIds((ids) => [...ids, item.id]);
    setError('');
    try {
      const saved = await api.updateFolderCollectionItem(collectionId, item.id, {
        channel_id: next.channel_id,
        channel_ref: next.channel_ref,
        admin_contact: next.admin_contact,
        role: next.role,
      });
      replaceCollectionItem(collectionId, item.id, saved);
    } catch (err) {
      replaceCollectionItem(collectionId, item.id, item);
      setError(err instanceof Error ? err.message : collectionUi.saveFailed);
    } finally {
      setSavingItemIds((ids) => ids.filter((id) => id !== item.id));
    }
  }

  async function createCollection() {
    if (!selectedTableId || isCreating) return;
    setIsCreating(true);
    setError('');
    try {
      const collection = await api.createFolderCollection(selectedTableId, collectionUi.newFolder);
      setCollections((items) => [...items, collection]);
      setExpandedCollectionIds((ids) => [...ids, collection.id]);
    } catch (err) {
      setError(err instanceof Error ? err.message : collectionUi.saveFailed);
    } finally {
      setIsCreating(false);
    }
  }

  async function saveCollectionTitle(collectionId: number, title: string) {
    const normalizedTitle = title.trim() || collectionUi.newFolder;
    setCollections((items) => items.map((item) => (
      item.id === collectionId ? { ...item, title: normalizedTitle } : item
    )));
    setError('');
    try {
      const saved = await api.updateFolderCollection(collectionId, normalizedTitle);
      setCollections((items) => items.map((item) => (
        item.id === collectionId ? { ...item, title: saved.title, updated_at: saved.updated_at } : item
      )));
    } catch (err) {
      setError(err instanceof Error ? err.message : collectionUi.saveFailed);
    }
  }

  async function deleteCollection(collectionId: number) {
    setError('');
    try {
      await api.deleteFolderCollection(collectionId);
      setCollections((items) => items.filter((item) => item.id !== collectionId));
      setExpandedCollectionIds((ids) => ids.filter((id) => id !== collectionId));
      setDeleteConfirmId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : collectionUi.deleteFailed);
    }
  }

  async function addItem(collectionId: number) {
    setError('');
    try {
      const item = await api.addFolderCollectionItem(collectionId);
      setCollections((items) => items.map((collection) => (
        collection.id === collectionId
          ? { ...collection, items: [...collection.items, item] }
          : collection
      )));
    } catch (err) {
      setError(err instanceof Error ? err.message : collectionUi.saveFailed);
    }
  }

  async function deleteItem(collectionId: number, itemId: number) {
    setSavingItemIds((ids) => [...ids, itemId]);
    setError('');
    try {
      await api.deleteFolderCollectionItem(collectionId, itemId);
      setCollections((items) => items.map((collection) => (
        collection.id === collectionId
          ? { ...collection, items: collection.items.filter((item) => item.id !== itemId) }
          : collection
      )));
      if (openItemMenu?.itemId === itemId) setOpenItemMenu(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : collectionUi.deleteFailed);
    } finally {
      setSavingItemIds((ids) => ids.filter((id) => id !== itemId));
    }
  }

  function commitChannelRef(
    collectionId: number,
    item: ApiFolderCollectionItem,
    value: string,
  ) {
    const channel = findChannelByRef(channels, value);
    const channelRef = channel ? (channel.url || `@${channel.username}`) : value.trim();
    void persistItem(collectionId, item, {
      channel_id: channel?.channel_id || null,
      channel_ref: channelRef,
    });
  }

  function toggleCollection(collectionId: number) {
    setExpandedCollectionIds((ids) => (
      ids.includes(collectionId)
        ? ids.filter((id) => id !== collectionId)
        : [...ids, collectionId]
    ));
  }

  return (
    <>
      <header className="topBar collectionTopBar">
        <div>
          <h1>{collectionUi.title}</h1>
          <p>{collectionUi.subtitle}</p>
        </div>
        <TableSelector
          tables={tables}
          selectedTable={selectedTable}
          isOpen={isTableMenuOpen}
          onToggle={() => setIsTableMenuOpen((value) => !value)}
          onSelect={(tableId) => {
            setSelectedTableId(tableId);
            setIsTableMenuOpen(false);
          }}
        />
      </header>

      {error && <div className="folderInlineError collectionError">{error}</div>}

      {isLoading ? (
        <LoadingState />
      ) : (
        <section className="folderCollectionWorkspace">
          {!collections.length && (
            <div className="collectionEmptyState">
              <span className="collectionEmptyIcon"><FolderOpen size={28} /></span>
              <strong>{collectionUi.emptyTitle}</strong>
              <p>{selectedTable ? collectionUi.emptyText : collectionUi.noTables}</p>
            </div>
          )}

          <div className="folderCollectionList">
            <AnimatePresence initial={false}>
              {collections.map((collection, collectionIndex) => {
                const isExpanded = expandedCollectionIds.includes(collection.id);
                const selectedChannelIds = new Set(
                  collection.items
                    .map((item) => item.channel_id)
                    .filter((channelId): channelId is number => channelId !== null),
                );
                return (
                  <motion.article
                    className={`folderCollectionCard${isExpanded ? ' isExpanded' : ''}`}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.2, delay: Math.min(collectionIndex * 0.04, 0.2) }}
                    key={collection.id}
                  >
                    <header className="folderCollectionHeader">
                      <button
                        className="folderCollectionToggle"
                        type="button"
                        onClick={() => toggleCollection(collection.id)}
                        aria-label={isExpanded ? 'Свернуть папку' : 'Раскрыть папку'}
                      >
                        <span className="folderCollectionGlyph"><FolderOpen size={19} /></span>
                        <ChevronDown className="folderCollectionChevron" size={17} />
                      </button>
                      <input
                        className="folderCollectionTitleInput"
                        value={collection.title}
                        onChange={(event) => {
                          const title = event.currentTarget.value;
                          setCollections((items) => items.map((item) => (
                            item.id === collection.id ? { ...item, title } : item
                          )));
                        }}
                        onBlur={(event) => void saveCollectionTitle(collection.id, event.currentTarget.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') event.currentTarget.blur();
                        }}
                        aria-label="Название папки"
                      />
                      <span className="folderCollectionCount">{formatChannelsCount(collection.items.length)}</span>
                      <div className="folderCollectionDelete">
                        {deleteConfirmId === collection.id ? (
                          <div className="collectionDeleteConfirm">
                            <span>{collectionUi.confirmDelete}</span>
                            <button type="button" onClick={() => void deleteCollection(collection.id)}>
                              <Check size={15} />
                            </button>
                            <button type="button" onClick={() => setDeleteConfirmId(null)}>
                              <X size={15} />
                            </button>
                          </div>
                        ) : (
                          <button
                            className="inlineIconButton collectionDeleteButton"
                            type="button"
                            onClick={() => setDeleteConfirmId(collection.id)}
                            title={collectionUi.deleteFolder}
                            aria-label={collectionUi.deleteFolder}
                          >
                            <Trash2 size={16} />
                          </button>
                        )}
                      </div>
                    </header>

                    <AnimatePresence initial={false}>
                      {isExpanded && (
                        <motion.div
                          className="folderCollectionBody"
                          initial={{ opacity: 0, y: -8 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -8 }}
                          transition={{ duration: 0.18 }}
                        >
                          <div className="folderCollectionTableScroll">
                            <table className="folderCollectionTable">
                              <thead>
                                <tr>
                                  <th>{collectionUi.channel}</th>
                                  <th>{collectionUi.admin}</th>
                                  <th>{collectionUi.role}</th>
                                  <th>{collectionUi.folders}</th>
                                  <th>{collectionUi.subscribers}</th>
                                  <th>{collectionUi.avgViews}</th>
                                  <th aria-label="Действия" />
                                </tr>
                              </thead>
                              <tbody>
                                {collection.items.map((item) => {
                                  const channel = item.channel_id ? channelById.get(item.channel_id) || null : null;
                                  const sortedSources = channel
                                    ? [...channel.source_channels].sort((left, right) => (
                                        Number(selectedChannelIds.has(Number(right.id)))
                                        - Number(selectedChannelIds.has(Number(left.id)))
                                      ))
                                    : [];
                                  const hasCurrentIntersection = sortedSources.some((source) => selectedChannelIds.has(Number(source.id)));
                                  const isSourcesOpen = openItemMenu?.type === 'sources' && openItemMenu.itemId === item.id;
                                  const isRoleOpen = openItemMenu?.type === 'role' && openItemMenu.itemId === item.id;
                                  const isSaving = savingItemIds.includes(item.id);
                                  return (
                                    <tr className={isSaving ? 'isSaving' : ''} key={item.id}>
                                      <td>
                                        {channel ? (
                                          <div className="collectionChannelChip">
                                            <CollectionChannelAvatar src={channel.avatar_url} title={channel.title} />
                                            <span>
                                              <strong>{channel.title}</strong>
                                              <em>{channel.username ? `@${channel.username.replace(/^@/, '')}` : channel.url}</em>
                                            </span>
                                            <button
                                              type="button"
                                              onClick={() => void persistItem(collection.id, item, { channel_id: null, channel_ref: '' })}
                                              title={collectionUi.removeChannel}
                                              aria-label={collectionUi.removeChannel}
                                              disabled={isSaving}
                                            >
                                              <X size={14} />
                                            </button>
                                          </div>
                                        ) : (
                                          <label className="collectionInputShell">
                                            <input
                                              value={item.channel_ref}
                                              onChange={(event) => patchCollectionItem(collection.id, item.id, {
                                                channel_id: null,
                                                channel_ref: event.currentTarget.value,
                                              })}
                                              onBlur={(event) => commitChannelRef(collection.id, item, event.currentTarget.value)}
                                              onKeyDown={(event) => {
                                                if (event.key === 'Enter') event.currentTarget.blur();
                                              }}
                                              placeholder={collectionUi.channelPlaceholder}
                                              disabled={isSaving}
                                            />
                                          </label>
                                        )}
                                      </td>
                                      <td>
                                        <label className="collectionInputShell adminInput">
                                          <input
                                            value={item.admin_contact}
                                            onChange={(event) => patchCollectionItem(collection.id, item.id, {
                                              admin_contact: event.currentTarget.value,
                                            })}
                                            onBlur={(event) => void persistItem(collection.id, item, {
                                              admin_contact: event.currentTarget.value,
                                            })}
                                            onKeyDown={(event) => {
                                              if (event.key === 'Enter') event.currentTarget.blur();
                                            }}
                                            placeholder={collectionUi.adminPlaceholder}
                                            disabled={isSaving}
                                          />
                                        </label>
                                      </td>
                                      <td>
                                        <div className={`collectionRoleSelect${isRoleOpen ? ' isOpen' : ''}`}>
                                          <button
                                            className={`collectionRoleButton ${item.role}`}
                                            type="button"
                                            onClick={() => setOpenItemMenu(isRoleOpen ? null : { type: 'role', itemId: item.id })}
                                            disabled={isSaving}
                                          >
                                            <span>{item.role === 'sponsor' ? collectionUi.sponsor : collectionUi.member}</span>
                                            <ChevronDown size={14} />
                                          </button>
                                          {isRoleOpen && (
                                            <div className="collectionRoleMenu">
                                              {(['member', 'sponsor'] as FolderCollectionRole[]).map((role) => (
                                                <button
                                                  className={`${role}${item.role === role ? ' isSelected' : ''}`}
                                                  type="button"
                                                  onClick={() => {
                                                    setOpenItemMenu(null);
                                                    void persistItem(collection.id, item, { role });
                                                  }}
                                                  key={role}
                                                >
                                                  {item.role === role && <Check size={14} />}
                                                  {role === 'sponsor' ? collectionUi.sponsor : collectionUi.member}
                                                </button>
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                      </td>
                                      <td>
                                        <div className="collectionSourcesCell">
                                          {channel && sortedSources.length ? (
                                            <>
                                              <button
                                                className={`collectionSourcesButton${hasCurrentIntersection ? ' hasIntersection' : ''}${isSourcesOpen ? ' isOpen' : ''}`}
                                                type="button"
                                                onClick={() => setOpenItemMenu(isSourcesOpen ? null : { type: 'sources', itemId: item.id })}
                                              >
                                                <span>{formatChannelsCount(sortedSources.length)}</span>
                                                <ChevronDown size={14} />
                                              </button>
                                              {isSourcesOpen && (
                                                <div className="collectionSourcesMenu">
                                                  {sortedSources.map((source) => {
                                                    const isInCollection = selectedChannelIds.has(Number(source.id));
                                                    return (
                                                      <div className={isInCollection ? 'isIntersection' : ''} key={source.id}>
                                                        <CollectionChannelAvatar src={source.avatar_url} title={source.title} small />
                                                        <span>{source.title}</span>
                                                        {isInCollection && <Check size={14} />}
                                                      </div>
                                                    );
                                                  })}
                                                </div>
                                              )}
                                            </>
                                          ) : (
                                            <span className="collectionEmptyMetric">{collectionUi.noIntersections}</span>
                                          )}
                                        </div>
                                      </td>
                                      <td className="collectionMetric">
                                        {channel ? formatMetric(channel.subscribers) : '—'}
                                      </td>
                                      <td className="collectionMetric">
                                        {channel ? formatMetric(channel.avg_views) : '—'}
                                      </td>
                                      <td>
                                        <button
                                          className="inlineIconButton collectionRowDelete"
                                          type="button"
                                          onClick={() => void deleteItem(collection.id, item.id)}
                                          title={collectionUi.deleteRow}
                                          aria-label={collectionUi.deleteRow}
                                          disabled={isSaving}
                                        >
                                          {isSaving ? <Loader2 className="spinIcon" size={15} /> : <Trash2 size={15} />}
                                        </button>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                          {!collection.items.length && (
                            <div className="collectionRowsEmpty">
                              <span>{collectionUi.noRows}</span>
                            </div>
                          )}
                          <button
                            className="collectionAddChannelButton"
                            type="button"
                            onClick={() => void addItem(collection.id)}
                          >
                            <Plus size={16} />
                            {collectionUi.addChannel}
                          </button>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.article>
                );
              })}
            </AnimatePresence>
          </div>

          <button
            className="collectionCreateButton"
            type="button"
            onClick={() => void createCollection()}
            disabled={!selectedTableId || isCreating}
            title={collectionUi.create}
            aria-label={collectionUi.create}
          >
            {isCreating ? <Loader2 className="spinIcon" size={25} /> : <Plus size={28} />}
          </button>
        </section>
      )}
    </>
  );
}
