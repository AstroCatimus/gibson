/**
 * Gibson — Inventory Screen.
 * Tap a book to edit price, condition, section, or delete it.
 * Filter by store, condition, status, or unpriced items.
 * Sort by newest, title, or price.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, FlatList, TextInput,
  TouchableOpacity, ActivityIndicator, Modal, ScrollView,
  Switch, Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../../src/lib/api';
import { C, COND_COLOR } from '../../src/lib/theme';

const GRADES   = ['Fine', 'Very Good+', 'Very Good', 'Good+', 'Good', 'Fair', 'Poor'];
const STATUSES = ['AVAILABLE', 'LISTED', 'HOLD', 'IN_STORE_ONLY', 'WITHDRAWN'];

const STATUS_LABEL = {
  AVAILABLE:    'Available',
  LISTED:       'Listed',
  HOLD:         'On Hold',
  IN_STORE_ONLY:'In-Store',
  WITHDRAWN:    'Withdrawn',
};

// Chips shown in the filter bar (status subset — not all statuses)
const FILTER_STATUSES = [
  { key: 'LISTED',        label: 'Listed' },
  { key: 'IN_STORE_ONLY', label: 'In-Store' },
  { key: 'GHOST_BOOK_QUEUE', label: 'Ghost' },
  { key: 'AVAILABLE',     label: 'Available' },
];

const SORT_OPTIONS = [
  { key: 'newest',     label: 'Newest',    icon: 'time-outline' },
  { key: 'title_asc',  label: 'A – Z',     icon: 'text-outline' },
  { key: 'price_asc',  label: 'Price ↑',   icon: 'arrow-up-outline' },
  { key: 'price_desc', label: 'Price ↓',   icon: 'arrow-down-outline' },
];

const PAGE = 50;

export default function InventoryScreen() {
  // ── Data ────────────────────────────────────────────────────────
  const [items, setItems]         = useState([]);
  const [stats, setStats]         = useState(null);
  const [loading, setLoading]     = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset]       = useState(0);
  const [hasMore, setHasMore]     = useState(true);

  // ── Search ──────────────────────────────────────────────────────
  const [query, setQuery]         = useState('');
  const [searching, setSearching] = useState(false);

  // ── Stores ──────────────────────────────────────────────────────
  const [stores, setStores]             = useState([]);
  const [selectedStoreId, setSelectedStoreId] = useState(null);

  // ── Filters ─────────────────────────────────────────────────────
  const [filterCondition, setFilterCondition] = useState('');
  const [filterStatus,    setFilterStatus]    = useState('');
  const [filterSection,   setFilterSection]   = useState('');
  const [filterNoPrice,   setFilterNoPrice]   = useState(false);
  const [sortKey,         setSortKey]         = useState('newest');
  const sortIdx = useRef(0);

  // ── Section picker ──────────────────────────────────────────────
  const [sections, setSections] = useState([]);
  const [sectionPickerOpen, setSectionPickerOpen] = useState(false);
  const [sectionPickerQuery, setSectionPickerQuery] = useState('');

  // ── Edit modal ──────────────────────────────────────────────────
  const [editing,     setEditing]   = useState(null);
  const [saving,      setSaving]    = useState(false);
  const [sectionSearch, setSectionSearch] = useState('');
  const [ePrice,      setEPrice]    = useState('');
  const [eCondition,  setECondition] = useState('');
  const [eSection,    setESection]  = useState('');
  const [eStatus,     setEStatus]   = useState('');
  const [eNotes,      setENotes]    = useState('');
  const [eSigned,     setESigned]   = useState(false);
  const [eInscribed,  setEInscribed] = useState(false);

  // ── Derived filter query string ─────────────────────────────────
  function buildParams(extra = {}) {
    const p = new URLSearchParams();
    p.set('limit', String(PAGE));
    p.set('offset', String(extra.offset ?? 0));
    p.set('sort', extra.sort ?? sortKey);
    if (extra.condition ?? filterCondition) p.set('condition', extra.condition ?? filterCondition);
    if (extra.status    ?? filterStatus)    p.set('status',    extra.status    ?? filterStatus);
    if (extra.section   ?? filterSection)   p.set('section',   extra.section   ?? filterSection);
    if (extra.noPrice   ?? filterNoPrice)   p.set('no_price',  'true');
    return '?' + p.toString();
  }

  // ── Load / reload ───────────────────────────────────────────────
  useEffect(() => {
    loadAll();
    loadStores();
  }, []);

  async function loadStores() {
    try {
      const res = await api.getMyStores();
      setStores(res.stores || []);
    } catch (e) { console.warn('loadStores', e); }
  }

  async function loadAll(overrides = {}) {
    setLoading(true);
    setOffset(0);
    setHasMore(true);
    const storeId = overrides.storeId ?? selectedStoreId;
    try {
      const [inv, st, sec] = await Promise.all([
        api.getInventory(buildParams({ ...overrides, offset: 0 }), storeId),
        api.getInventoryStats(storeId),
        api.getSections(),
      ]);
      const list = inv.items || inv || [];
      setItems(list);
      setOffset(list.length);
      setHasMore(list.length === PAGE);
      setStats(st);
      setSections(sec.sections || []);
    } catch (e) { console.warn(e); }
    finally { setLoading(false); }
  }

  async function loadMore() {
    if (loadingMore || !hasMore || query) return;
    setLoadingMore(true);
    try {
      const inv  = await api.getInventory(buildParams({ offset }), selectedStoreId);
      const list = inv.items || inv || [];
      setItems(prev => [...prev, ...list]);
      setOffset(prev => prev + list.length);
      setHasMore(list.length === PAGE);
    } catch (e) { console.warn(e); }
    finally { setLoadingMore(false); }
  }

  // ── Filter / sort helpers ───────────────────────────────────────
  function applyFilter(patch) {
    const next = {
      condition: filterCondition,
      status:    filterStatus,
      section:   filterSection,
      noPrice:   filterNoPrice,
      sort:      sortKey,
      ...patch,
    };
    if (patch.condition !== undefined) setFilterCondition(patch.condition);
    if (patch.status    !== undefined) setFilterStatus(patch.status);
    if (patch.section   !== undefined) setFilterSection(patch.section);
    if (patch.noPrice   !== undefined) setFilterNoPrice(patch.noPrice);
    if (patch.sort      !== undefined) setSortKey(patch.sort);
    setQuery('');
    loadAll(next);
  }

  function cycleSort() {
    sortIdx.current = (sortIdx.current + 1) % SORT_OPTIONS.length;
    const next = SORT_OPTIONS[sortIdx.current].key;
    applyFilter({ sort: next });
  }

  function selectStore(id) {
    setSelectedStoreId(id);
    loadAll({ storeId: id });
  }

  // ── Search ──────────────────────────────────────────────────────
  async function handleSearch(text) {
    setQuery(text);
    if (!text.trim()) { loadAll(); return; }
    setSearching(true);
    try {
      const results = await api.searchCatalogue(text);
      setItems(results.items || results || []);
    } catch (e) { console.warn(e); }
    finally { setSearching(false); }
  }

  // ── Edit modal ──────────────────────────────────────────────────
  function openEdit(item) {
    setEditing(item);
    setEPrice(item.asking_price != null ? String(item.asking_price) : '');
    setECondition(item.condition_grade || '');
    setESection(item.section || '');
    setEStatus(item.status || 'AVAILABLE');
    setENotes(item.condition_notes || '');
    setESigned(item.is_signed || false);
    setEInscribed(item.is_inscribed || false);
    setSectionSearch('');
  }

  async function handleSave() {
    setSaving(true);
    try {
      const loc = sections.find(s => s.section === eSection);
      await api.updateItem(editing.stock_item_id, {
        asking_price:    ePrice ? parseFloat(ePrice) : null,
        condition_grade: eCondition || null,
        condition_notes: eNotes || null,
        status:          eStatus,
        location_id:     loc ? String(loc.location_id) : null,
        is_signed:       eSigned,
        is_inscribed:    eInscribed,
      });
      setItems(prev => prev.map(i =>
        i.stock_item_id === editing.stock_item_id
          ? { ...i, asking_price: ePrice ? parseFloat(ePrice) : null,
              condition_grade: eCondition, condition_notes: eNotes || null,
              status: eStatus, section: eSection,
              is_signed: eSigned, is_inscribed: eInscribed }
          : i
      ));
      setEditing(null);
    } catch (e) {
      Alert.alert('Error', e.message);
    } finally {
      setSaving(false);
    }
  }

  function handleDelete() {
    Alert.alert(
      'Remove from inventory?',
      `"${editing.title}" will be marked withdrawn.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove', style: 'destructive',
          onPress: async () => {
            try {
              await api.deleteItem(editing.stock_item_id);
              setItems(prev => prev.filter(i => i.stock_item_id !== editing.stock_item_id));
              setEditing(null);
            } catch (e) {
              Alert.alert('Error', e.message);
            }
          },
        },
      ],
    );
  }

  // ── Render item ─────────────────────────────────────────────────
  function renderItem({ item }) {
    const condColor   = COND_COLOR[item.condition_grade] || C.text3;
    const noPrice     = item.asking_price == null;
    return (
      <TouchableOpacity style={s.item} onPress={() => openEdit(item)} activeOpacity={0.7}>
        <View style={[s.condStripe, { backgroundColor: condColor }]} />
        <View style={s.itemBody}>
          <View style={s.itemMain}>
            <Text style={s.itemTitle} numberOfLines={1}>{item.title || 'Untitled'}</Text>
            <Text style={s.itemAuthor} numberOfLines={1}>{item.author || ''}</Text>
            {item.publisher ? (
              <Text style={s.itemPublisher} numberOfLines={1}>{item.publisher}</Text>
            ) : null}
            {item.condition_notes ? (
              <Text style={s.itemNotes} numberOfLines={2}>{item.condition_notes}</Text>
            ) : null}
            <View style={s.itemMeta}>
              {item.gibson_sku ? (
                <Text style={s.itemSku}>{item.gibson_sku}</Text>
              ) : null}
              {item.section ? (
                <View style={s.sectionPill}>
                  <Text style={s.sectionPillText}>{item.section}</Text>
                </View>
              ) : null}
              {noPrice ? (
                <View style={[s.sectionPill, { borderColor: C.red, backgroundColor: C.redBg }]}>
                  <Text style={[s.sectionPillText, { color: C.red }]}>No price</Text>
                </View>
              ) : null}
            </View>
          </View>
          <View style={s.itemRight}>
            <Text style={[s.itemPrice, noPrice && { color: C.text3, fontSize: 13 }]}>
              {noPrice ? '—' : `$${item.asking_price.toFixed(2)}`}
            </Text>
            {item.condition_grade ? (
              <Text style={[s.condLabel, { color: condColor }]}>{item.condition_grade}</Text>
            ) : null}
          </View>
        </View>
      </TouchableOpacity>
    );
  }

  // ── Sort button ─────────────────────────────────────────────────
  const currentSort = SORT_OPTIONS.find(o => o.key === sortKey) || SORT_OPTIONS[0];

  // ── Active filter count (badge) ─────────────────────────────────
  const activeFilters = [filterCondition, filterStatus, filterSection, filterNoPrice].filter(Boolean).length;

  // ── Section picker filtered results ────────────────────────────
  const filteredSections = sectionPickerQuery
    ? sections.filter(l => l.section?.toLowerCase().includes(sectionPickerQuery.toLowerCase())).slice(0, 40)
    : sections.slice(0, 40);

  return (
    <View style={s.container}>

      {/* ── Store tabs (only if user belongs to multiple stores) ── */}
      {stores.length > 1 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={s.storeTabs}
          contentContainerStyle={s.storeTabsContent}
        >
          <TouchableOpacity
            style={[s.storeTab, !selectedStoreId && s.storeTabActive]}
            onPress={() => selectStore(null)}
          >
            <Text style={[s.storeTabText, !selectedStoreId && s.storeTabTextActive]}>All</Text>
          </TouchableOpacity>
          {stores.map(store => (
            <TouchableOpacity
              key={store.store_id}
              style={[s.storeTab, selectedStoreId === store.store_id && s.storeTabActive]}
              onPress={() => selectStore(store.store_id)}
            >
              <Text style={[s.storeTabText, selectedStoreId === store.store_id && s.storeTabTextActive]}>
                {store.prefix || store.name}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      )}

      {/* ── Stats banner ── */}
      {stats && (
        <View style={s.statsRow}>
          <View style={s.stat}>
            <Text style={s.statNum}>{stats.available ?? 0}</Text>
            <Text style={s.statLabel}>Available</Text>
          </View>
          <View style={[s.stat, s.statDivider]}>
            <Text style={s.statNum}>{stats.total ?? 0}</Text>
            <Text style={s.statLabel}>Total</Text>
          </View>
          <View style={[s.stat, s.statDivider]}>
            <Text style={[s.statNum, { color: C.red }]}>{stats.pending_id ?? 0}</Text>
            <Text style={s.statLabel}>Unidentified</Text>
          </View>
          <View style={s.stat}>
            <Text style={[s.statNum, { color: C.accent }]}>
              ${(stats.total_value || 0).toFixed(0)}
            </Text>
            <Text style={s.statLabel}>Value</Text>
          </View>
        </View>
      )}

      {/* ── Search + Sort ── */}
      <View style={s.searchRow}>
        <View style={s.searchBar}>
          <Ionicons name="search-outline" size={16} color={C.text3} style={{ marginRight: 8 }} />
          <TextInput
            style={s.searchInput}
            value={query}
            onChangeText={handleSearch}
            placeholder="Search title, author, ISBN…"
            placeholderTextColor={C.text3}
            returnKeyType="search"
          />
          {searching
            ? <ActivityIndicator color={C.accent} size="small" />
            : query.length > 0
              ? (
                <TouchableOpacity onPress={() => handleSearch('')} style={s.clearBtn}>
                  <Ionicons name="close-circle" size={16} color={C.text3} />
                </TouchableOpacity>
              ) : null
          }
        </View>
        <TouchableOpacity style={s.sortBtn} onPress={cycleSort}>
          <Ionicons name={currentSort.icon} size={14} color={C.accent} />
          <Text style={s.sortBtnText}>{currentSort.label}</Text>
        </TouchableOpacity>
      </View>

      {/* ── Filter chips ── */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={s.filterRow}
        contentContainerStyle={s.filterRowContent}
      >
        {/* Unpriced */}
        <TouchableOpacity
          style={[s.filterChip, filterNoPrice && s.filterChipDanger]}
          onPress={() => applyFilter({ noPrice: !filterNoPrice })}
        >
          <Text style={[s.filterChipText, filterNoPrice && s.filterChipTextDanger]}>
            Unpriced
          </Text>
        </TouchableOpacity>

        {/* Status chips */}
        {FILTER_STATUSES.map(({ key, label }) => (
          <TouchableOpacity
            key={key}
            style={[s.filterChip, filterStatus === key && s.filterChipActive]}
            onPress={() => applyFilter({ status: filterStatus === key ? '' : key })}
          >
            <Text style={[s.filterChipText, filterStatus === key && s.filterChipTextActive]}>
              {label}
            </Text>
          </TouchableOpacity>
        ))}

        {/* Condition chips */}
        {['Fine', 'Very Good+', 'Very Good', 'Good', 'Poor'].map(g => {
          const active = filterCondition === g;
          const col    = COND_COLOR[g] || C.text3;
          return (
            <TouchableOpacity
              key={g}
              style={[s.filterChip, active && { borderColor: col, backgroundColor: col + '22' }]}
              onPress={() => applyFilter({ condition: active ? '' : g })}
            >
              <Text style={[s.filterChipText, active && { color: col, fontWeight: '700' }]}>{g}</Text>
            </TouchableOpacity>
          );
        })}

        {/* Section picker chip */}
        <TouchableOpacity
          style={[s.filterChip, filterSection && s.filterChipActive]}
          onPress={() => { setSectionPickerOpen(true); setSectionPickerQuery(''); }}
        >
          <Ionicons
            name="library-outline"
            size={12}
            color={filterSection ? C.accent : C.text3}
            style={{ marginRight: 4 }}
          />
          <Text style={[s.filterChipText, filterSection && s.filterChipTextActive]}>
            {filterSection || 'Section'}
          </Text>
          {filterSection ? (
            <TouchableOpacity
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              onPress={e => { e.stopPropagation(); applyFilter({ section: '' }); }}
              style={{ marginLeft: 4 }}
            >
              <Ionicons name="close-circle" size={13} color={C.accent} />
            </TouchableOpacity>
          ) : null}
        </TouchableOpacity>

        {/* Clear all filters */}
        {activeFilters > 0 && (
          <TouchableOpacity
            style={[s.filterChip, { borderColor: C.text3 }]}
            onPress={() => applyFilter({ condition: '', status: '', section: '', noPrice: false })}
          >
            <Ionicons name="close" size={12} color={C.text3} style={{ marginRight: 3 }} />
            <Text style={s.filterChipText}>Clear</Text>
          </TouchableOpacity>
        )}
      </ScrollView>

      {/* ── List ── */}
      {loading
        ? <ActivityIndicator color={C.accent} style={{ marginTop: 48 }} />
        : (
          <FlatList
            data={items}
            keyExtractor={item => item.stock_item_id || String(Math.random())}
            renderItem={renderItem}
            onEndReached={loadMore}
            onEndReachedThreshold={0.3}
            contentContainerStyle={items.length === 0 ? s.emptyContainer : { paddingBottom: 20 }}
            ListEmptyComponent={
              <View style={s.emptyWrap}>
                <Text style={s.emptyIcon}>📚</Text>
                <Text style={s.emptyTitle}>No books found</Text>
                <Text style={s.emptyHint}>
                  {query ? 'Try a different search'
                    : activeFilters ? 'No items match the active filters'
                    : 'Inventory is empty'}
                </Text>
              </View>
            }
            ListFooterComponent={
              loadingMore
                ? <ActivityIndicator color={C.accent} style={{ marginVertical: 16 }} />
                : null
            }
          />
        )
      }

      {/* ── Section picker modal ── */}
      <Modal
        visible={sectionPickerOpen}
        animationType="slide"
        transparent
        onRequestClose={() => setSectionPickerOpen(false)}
      >
        <View style={s.modalOverlay}>
          <View style={[s.modalSheet, { maxHeight: '60%' }]}>
            <View style={s.sheetHandle} />
            <View style={s.pickerHeader}>
              <Text style={s.pickerTitle}>Filter by Section</Text>
              <TouchableOpacity onPress={() => setSectionPickerOpen(false)}>
                <Ionicons name="close" size={22} color={C.text2} />
              </TouchableOpacity>
            </View>
            <View style={{ paddingHorizontal: 16, paddingBottom: 8 }}>
              <View style={s.searchBar}>
                <Ionicons name="search-outline" size={14} color={C.text3} style={{ marginRight: 6 }} />
                <TextInput
                  style={s.searchInput}
                  value={sectionPickerQuery}
                  onChangeText={setSectionPickerQuery}
                  placeholder="Search sections…"
                  placeholderTextColor={C.text3}
                  autoFocus
                />
              </View>
            </View>
            <FlatList
              data={filteredSections}
              keyExtractor={l => String(l.location_id)}
              keyboardShouldPersistTaps="handled"
              renderItem={({ item: loc }) => (
                <TouchableOpacity
                  style={[s.pickerRow, filterSection === loc.section && s.pickerRowActive]}
                  onPress={() => {
                    applyFilter({ section: filterSection === loc.section ? '' : loc.section });
                    setSectionPickerOpen(false);
                  }}
                >
                  <Text style={[s.pickerRowText, filterSection === loc.section && { color: C.accent }]}>
                    {loc.section}
                  </Text>
                  {filterSection === loc.section && (
                    <Ionicons name="checkmark" size={16} color={C.accent} />
                  )}
                </TouchableOpacity>
              )}
              ListEmptyComponent={
                <Text style={{ color: C.text3, textAlign: 'center', padding: 24 }}>No sections found</Text>
              }
            />
          </View>
        </View>
      </Modal>

      {/* ── Edit modal ── */}
      <Modal visible={!!editing} animationType="slide" transparent onRequestClose={() => setEditing(null)}>
        <View style={s.modalOverlay}>
          <View style={s.modalSheet}>

            <View style={s.sheetHandle} />

            <ScrollView contentContainerStyle={s.modalContent} showsVerticalScrollIndicator={false}>

              <View style={s.modalHeader}>
                <View style={{ flex: 1 }}>
                  <Text style={s.modalTitle} numberOfLines={2}>{editing?.title || 'Edit Book'}</Text>
                  {editing?.author ? (
                    <Text style={s.modalAuthor}>{editing.author}</Text>
                  ) : null}
                  {editing?.gibson_sku ? (
                    <Text style={s.modalSku}>{editing.gibson_sku}</Text>
                  ) : null}
                </View>
                <TouchableOpacity onPress={() => setEditing(null)} style={s.modalClose}>
                  <Ionicons name="close" size={22} color={C.text2} />
                </TouchableOpacity>
              </View>

              {/* Price */}
              <Text style={s.fieldLabel}>Asking Price</Text>
              <View style={s.priceRow}>
                <Text style={s.dollar}>$</Text>
                <TextInput
                  style={[s.input, { flex: 1 }]}
                  value={ePrice}
                  onChangeText={setEPrice}
                  keyboardType="decimal-pad"
                  placeholder="Leave blank if not priced yet"
                  placeholderTextColor={C.text3}
                />
              </View>
              {!ePrice ? (
                <Text style={s.noPriceHint}>This book will appear in Unpriced filter.</Text>
              ) : null}

              {/* Condition */}
              <Text style={s.fieldLabel}>Condition</Text>
              <View style={s.chipRow}>
                {GRADES.map(g => {
                  const color  = COND_COLOR[g] || C.text3;
                  const active = eCondition === g;
                  return (
                    <TouchableOpacity
                      key={g}
                      style={[s.chip, active && { borderColor: color, backgroundColor: color + '20' }]}
                      onPress={() => setECondition(g)}
                    >
                      <Text style={[s.chipText, active && { color, fontWeight: '700' }]}>{g}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              {/* Status */}
              <Text style={s.fieldLabel}>Status</Text>
              <View style={s.chipRow}>
                {STATUSES.map(st => (
                  <TouchableOpacity
                    key={st}
                    style={[s.chip, eStatus === st && s.chipActive]}
                    onPress={() => setEStatus(st)}
                  >
                    <Text style={[s.chipText, eStatus === st && s.chipTextActive]}>
                      {STATUS_LABEL[st] || st}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Section — searchable dropdown */}
              <Text style={s.fieldLabel}>Section</Text>
              <TextInput
                style={[s.input, { marginBottom: 8 }]}
                value={sectionSearch || eSection}
                onChangeText={t => { setSectionSearch(t); setESection(t); }}
                placeholder="Type to search sections…"
                placeholderTextColor={C.text3}
              />
              {sectionSearch.length > 0 && (
                <View style={{ maxHeight: 160, borderRadius: 8, overflow: 'hidden',
                               borderWidth: 1, borderColor: C.border, marginBottom: 8 }}>
                  <FlatList
                    data={sections
                      .filter(l => l.section?.toLowerCase().includes(sectionSearch.toLowerCase()))
                      .slice(0, 30)}
                    keyExtractor={l => String(l.location_id)}
                    renderItem={({ item: loc }) => (
                      <TouchableOpacity
                        style={{ padding: 12, borderBottomWidth: 1, borderBottomColor: C.border,
                                 backgroundColor: eSection === loc.section ? C.accentBg : C.card }}
                        onPress={() => { setESection(loc.section); setSectionSearch(''); }}
                      >
                        <Text style={{ color: eSection === loc.section ? C.accent : C.text, fontSize: 14 }}>
                          {loc.section}
                        </Text>
                      </TouchableOpacity>
                    )}
                    keyboardShouldPersistTaps="handled"
                  />
                </View>
              )}

              {/* Condition notes */}
              <Text style={s.fieldLabel}>Condition Notes</Text>
              <TextInput
                style={[s.input, { minHeight: 80, textAlignVertical: 'top' }]}
                value={eNotes}
                onChangeText={setENotes}
                placeholder="Dealer notes on this copy's condition…"
                placeholderTextColor={C.text3}
                multiline
              />

              {/* Toggles */}
              <View style={s.toggleRow}>
                <View>
                  <Text style={s.toggleLabel}>Signed copy</Text>
                  <Text style={s.toggleHint}>Author's signature present</Text>
                </View>
                <Switch
                  value={eSigned}
                  onValueChange={setESigned}
                  thumbColor={eSigned ? C.accent : C.surface}
                  trackColor={{ false: C.border, true: C.accentBg }}
                />
              </View>
              <View style={[s.toggleRow, s.toggleBorder]}>
                <View>
                  <Text style={s.toggleLabel}>Inscribed copy</Text>
                  <Text style={s.toggleHint}>Personalized inscription inside</Text>
                </View>
                <Switch
                  value={eInscribed}
                  onValueChange={setEInscribed}
                  thumbColor={eInscribed ? C.accent : C.surface}
                  trackColor={{ false: C.border, true: C.accentBg }}
                />
              </View>

              {/* Actions */}
              <TouchableOpacity
                style={[s.saveBtn, saving && s.btnDisabled]}
                onPress={handleSave}
                disabled={saving}
              >
                {saving
                  ? <ActivityIndicator color={C.bg} />
                  : <Text style={s.saveBtnText}>Save Changes</Text>
                }
              </TouchableOpacity>

              <TouchableOpacity style={s.deleteBtn} onPress={handleDelete}>
                <Text style={s.deleteBtnText}>Remove from Inventory</Text>
              </TouchableOpacity>

            </ScrollView>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },

  // Store tabs
  storeTabs: { backgroundColor: C.surface, borderBottomWidth: 1, borderBottomColor: C.border },
  storeTabsContent: { paddingHorizontal: 12, paddingVertical: 8, gap: 8 },
  storeTab: {
    paddingHorizontal: 14, paddingVertical: 6, borderRadius: 999,
    borderWidth: 1, borderColor: C.border, backgroundColor: C.surface,
  },
  storeTabActive: { backgroundColor: C.accentBg, borderColor: C.accent },
  storeTabText: { color: C.text3, fontSize: 13, fontWeight: '500' },
  storeTabTextActive: { color: C.accent, fontWeight: '700' },

  // Stats
  statsRow: {
    flexDirection: 'row', backgroundColor: C.surface,
    paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: C.border,
  },
  stat: { flex: 1, alignItems: 'center' },
  statDivider: { borderLeftWidth: 1, borderColor: C.border },
  statNum: { color: C.text, fontSize: 20, fontWeight: '700' },
  statLabel: {
    color: C.text3, fontSize: 10, marginTop: 3,
    textTransform: 'uppercase', letterSpacing: 0.8,
  },

  // Search + sort row
  searchRow: {
    flexDirection: 'row', alignItems: 'center',
    marginHorizontal: 12, marginTop: 10, marginBottom: 0, gap: 8,
  },
  searchBar: {
    flex: 1, flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 12, paddingVertical: 9,
    backgroundColor: C.card, borderRadius: 10,
    borderWidth: 1, borderColor: C.border,
  },
  searchInput: { flex: 1, color: C.text, fontSize: 14 },
  clearBtn: { padding: 2 },
  sortBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 10, paddingVertical: 9,
    backgroundColor: C.card, borderRadius: 10,
    borderWidth: 1, borderColor: C.border,
  },
  sortBtnText: { color: C.accent, fontSize: 12, fontWeight: '600' },

  // Filter chips
  filterRow: { flexGrow: 0, marginTop: 8 },
  filterRowContent: { paddingHorizontal: 12, paddingBottom: 8, gap: 6 },
  filterChip: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 11, paddingVertical: 6,
    borderRadius: 999, borderWidth: 1, borderColor: C.border,
    backgroundColor: C.surface,
  },
  filterChipActive:     { borderColor: C.accent, backgroundColor: C.accentBg },
  filterChipDanger:     { borderColor: C.red,    backgroundColor: C.redBg },
  filterChipText:       { color: C.text3, fontSize: 12 },
  filterChipTextActive: { color: C.accent, fontWeight: '700' },
  filterChipTextDanger: { color: C.red,   fontWeight: '700' },

  // List items
  item: {
    flexDirection: 'row',
    borderBottomWidth: 1, borderBottomColor: C.border,
    backgroundColor: C.bg,
  },
  condStripe: { width: 3, minHeight: 70 },
  itemBody: {
    flex: 1, flexDirection: 'row',
    paddingHorizontal: 14, paddingVertical: 13, alignItems: 'center',
  },
  itemMain: { flex: 1, marginRight: 12 },
  itemTitle: { color: C.text, fontSize: 14, fontWeight: '600' },
  itemAuthor: { color: C.text2, fontSize: 12, marginTop: 2 },
  itemPublisher: { color: C.text3, fontSize: 11, marginTop: 1 },
  itemNotes: { color: C.text3, fontSize: 11, marginTop: 2, fontStyle: 'italic' },
  itemMeta: { flexDirection: 'row', gap: 6, marginTop: 5, alignItems: 'center', flexWrap: 'wrap' },
  itemSku: { color: C.text3, fontSize: 10, fontFamily: 'monospace' },
  sectionPill: {
    backgroundColor: C.surface, borderRadius: 4,
    paddingHorizontal: 6, paddingVertical: 1,
    borderWidth: 1, borderColor: C.border,
  },
  sectionPillText: { color: C.text3, fontSize: 10 },
  itemRight: { alignItems: 'flex-end', gap: 4 },
  itemPrice: { color: C.accent, fontSize: 16, fontWeight: '700' },
  condLabel: { fontSize: 11, fontWeight: '600' },

  emptyContainer: { flex: 1 },
  emptyWrap: { alignItems: 'center', marginTop: 80 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyTitle: { color: C.text, fontSize: 16, fontWeight: '600' },
  emptyHint: { color: C.text2, fontSize: 13, marginTop: 6, textAlign: 'center', paddingHorizontal: 32 },

  // Section picker modal
  pickerHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 20, paddingVertical: 12,
  },
  pickerTitle: { color: C.text, fontSize: 16, fontWeight: '700' },
  pickerRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 20, paddingVertical: 14,
    borderBottomWidth: 1, borderBottomColor: C.border,
  },
  pickerRowActive: { backgroundColor: C.accentBg },
  pickerRowText: { color: C.text, fontSize: 14 },

  // Edit modal
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.75)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: C.card, borderTopLeftRadius: 24, borderTopRightRadius: 24,
    maxHeight: '92%', borderTopWidth: 1, borderColor: C.border,
  },
  sheetHandle: {
    width: 36, height: 4, borderRadius: 2,
    backgroundColor: C.border, alignSelf: 'center', marginTop: 12,
  },
  modalContent: { padding: 20, paddingTop: 16, paddingBottom: 48 },
  modalHeader: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 20 },
  modalTitle:  { color: C.text, fontSize: 17, fontWeight: '700', lineHeight: 24 },
  modalAuthor: { color: C.text2, fontSize: 13, marginTop: 3 },
  modalSku:    { color: C.text3, fontSize: 11, fontFamily: 'monospace', marginTop: 5 },
  modalClose:  { padding: 4, marginLeft: 12 },

  fieldLabel: {
    color: C.text3, fontSize: 11, marginTop: 20, marginBottom: 8,
    textTransform: 'uppercase', letterSpacing: 0.8,
  },
  noPriceHint: {
    color: C.red, fontSize: 11, marginTop: 4, marginBottom: 4,
  },
  priceRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dollar: { color: C.text2, fontSize: 18, fontWeight: '600' },
  input: {
    backgroundColor: C.surface, borderWidth: 1, borderColor: C.border,
    borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10,
    color: C.text, fontSize: 14,
  },

  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    paddingHorizontal: 12, paddingVertical: 7, borderRadius: 16,
    borderWidth: 1, borderColor: C.border, backgroundColor: C.surface,
  },
  chipActive:     { backgroundColor: C.accentBg, borderColor: C.accent },
  chipText:       { color: C.text3, fontSize: 12 },
  chipTextActive: { color: C.accent, fontWeight: '700' },

  toggleRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', paddingVertical: 14,
  },
  toggleBorder: { borderTopWidth: 1, borderTopColor: C.border },
  toggleLabel:  { color: C.text, fontSize: 15, fontWeight: '500' },
  toggleHint:   { color: C.text3, fontSize: 11, marginTop: 2 },

  saveBtn: {
    backgroundColor: C.accent, padding: 16, borderRadius: 12,
    alignItems: 'center', marginTop: 24,
  },
  saveBtnText: { color: C.bg, fontWeight: '700', fontSize: 15 },
  btnDisabled: { opacity: 0.5 },
  deleteBtn:   { alignItems: 'center', padding: 14, marginTop: 4 },
  deleteBtnText: { color: C.red, fontSize: 14 },
});
