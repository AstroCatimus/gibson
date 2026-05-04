/**
 * Gibson — Inventory Screen.
 * Tap a book to edit price, condition, section, or delete it.
 */

import { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, FlatList, TextInput,
  TouchableOpacity, ActivityIndicator, Modal, ScrollView,
  Switch, Alert,
} from 'react-native';
import { api } from '../../src/lib/api';

const ACCENT = '#e94560';
const BG = '#0f0f1a';
const CARD = '#13131f';
const GREEN = '#2ecc71';

const COND_COLOR = {
  'Fine': '#2ecc71', 'Very Good+': '#27ae60', 'Very Good': '#3498db',
  'Good+': '#9b59b6', 'Good': '#f39c12', 'Fair': '#e67e22', 'Poor': '#e74c3c',
};
const GRADES = ['Fine', 'Very Good+', 'Very Good', 'Good+', 'Good', 'Fair', 'Poor'];
const STATUSES = ['AVAILABLE', 'LISTED', 'HOLD', 'IN_STORE_ONLY', 'WITHDRAWN'];

export default function InventoryScreen() {
  const [items, setItems]       = useState([]);
  const [stats, setStats]       = useState(null);
  const [query, setQuery]       = useState('');
  const [loading, setLoading]   = useState(true);
  const [searching, setSearching] = useState(false);

  const [editing, setEditing]   = useState(null);   // stock item being edited
  const [sections, setSections] = useState([]);
  const [saving, setSaving]     = useState(false);

  // edit fields
  const [ePrice, setEPrice]         = useState('');
  const [eCondition, setECondition] = useState('');
  const [eSection, setESection]     = useState('');
  const [eStatus, setEStatus]       = useState('');
  const [eSigned, setESigned]       = useState(false);
  const [eInscribed, setEInscribed] = useState(false);

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [inv, st, sec] = await Promise.all([
        api.getInventory('?limit=50'),
        api.getInventoryStats(),
        api.getSections(),
      ]);
      setItems(inv.items || inv || []);
      setStats(st);
      setSections(sec.sections || []);
    } catch (e) {
      console.warn(e);
    } finally {
      setLoading(false);
    }
  }

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

  function openEdit(item) {
    setEditing(item);
    setEPrice(item.asking_price != null ? String(item.asking_price) : '');
    setECondition(item.condition_grade || '');
    setESection(item.section || '');
    setEStatus(item.status || 'AVAILABLE');
    setESigned(item.is_signed || false);
    setEInscribed(item.is_inscribed || false);
  }

  async function handleSave() {
    setSaving(true);
    try {
      const loc = sections.find(s => s.section === eSection);
      await api.updateItem(editing.stock_item_id, {
        asking_price:   ePrice ? parseFloat(ePrice) : null,
        condition_grade: eCondition || null,
        status:          eStatus,
        location_id:     loc ? String(loc.location_id) : null,
        is_signed:       eSigned,
        is_inscribed:    eInscribed,
      });
      setItems(prev => prev.map(i =>
        i.stock_item_id === editing.stock_item_id
          ? { ...i, asking_price: ePrice ? parseFloat(ePrice) : null,
              condition_grade: eCondition, status: eStatus,
              section: eSection, is_signed: eSigned, is_inscribed: eInscribed }
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

  function renderItem({ item }) {
    const condColor = COND_COLOR[item.condition_grade] || '#555';
    return (
      <TouchableOpacity style={s.item} onPress={() => openEdit(item)} activeOpacity={0.7}>
        <View style={s.itemMain}>
          <Text style={s.itemTitle} numberOfLines={1}>{item.title || 'Untitled'}</Text>
          <Text style={s.itemAuthor} numberOfLines={1}>{item.author || ''}</Text>
          <View style={s.itemMeta}>
            {item.gibson_sku ? <Text style={s.itemSku}>{item.gibson_sku}</Text> : null}
            {item.section ? <Text style={s.itemSection}>{item.section}</Text> : null}
          </View>
        </View>
        <View style={s.itemRight}>
          <Text style={s.itemPrice}>${(item.asking_price || 0).toFixed(2)}</Text>
          {item.condition_grade ? (
            <View style={[s.condBadge, { borderColor: condColor }]}>
              <Text style={[s.condBadgeText, { color: condColor }]}>{item.condition_grade}</Text>
            </View>
          ) : null}
        </View>
      </TouchableOpacity>
    );
  }

  return (
    <View style={s.container}>
      {/* Stats */}
      {stats && (
        <View style={s.statsRow}>
          <View style={s.stat}>
            <Text style={s.statNum}>{stats.available ?? 0}</Text>
            <Text style={s.statLabel}>Available</Text>
          </View>
          <View style={[s.stat, s.statBorder]}>
            <Text style={s.statNum}>{stats.total ?? 0}</Text>
            <Text style={s.statLabel}>Total</Text>
          </View>
          <View style={s.stat}>
            <Text style={[s.statNum, { color: GREEN }]}>${(stats.total_value || 0).toFixed(0)}</Text>
            <Text style={s.statLabel}>Value</Text>
          </View>
        </View>
      )}

      {/* Search */}
      <View style={s.searchRow}>
        <View style={s.searchWrap}>
          <Text style={s.searchIcon}>⌕</Text>
          <TextInput
            style={s.searchInput}
            value={query}
            onChangeText={handleSearch}
            placeholder="Search title, author, ISBN…"
            placeholderTextColor="#444"
            returnKeyType="search"
          />
          {query.length > 0 && (
            <TouchableOpacity onPress={() => handleSearch('')} style={s.clearBtn}>
              <Text style={s.clearBtnText}>✕</Text>
            </TouchableOpacity>
          )}
        </View>
        {searching && <ActivityIndicator color={ACCENT} style={{ marginLeft: 8 }} />}
      </View>

      {loading
        ? <ActivityIndicator color={ACCENT} style={{ marginTop: 40 }} />
        : (
          <FlatList
            data={items}
            keyExtractor={item => item.stock_item_id || String(Math.random())}
            renderItem={renderItem}
            contentContainerStyle={items.length === 0 ? s.emptyContainer : { paddingBottom: 20 }}
            ListEmptyComponent={
              <View style={s.emptyWrap}>
                <Text style={s.emptyIcon}>📚</Text>
                <Text style={s.emptyTitle}>No books found</Text>
                <Text style={s.emptyHint}>{query ? 'Try a different search' : 'Inventory is empty'}</Text>
              </View>
            }
          />
        )
      }

      {/* Edit Modal */}
      <Modal visible={!!editing} animationType="slide" transparent onRequestClose={() => setEditing(null)}>
        <View style={s.modalOverlay}>
          <View style={s.modalSheet}>
            <ScrollView contentContainerStyle={s.modalContent}>

              <View style={s.modalHeader}>
                <Text style={s.modalTitle} numberOfLines={2}>{editing?.title || 'Edit Book'}</Text>
                <TouchableOpacity onPress={() => setEditing(null)} style={s.modalClose}>
                  <Text style={s.modalCloseText}>✕</Text>
                </TouchableOpacity>
              </View>

              {editing?.gibson_sku ? (
                <Text style={s.modalSku}>{editing.gibson_sku}</Text>
              ) : null}

              {/* Price */}
              <Text style={s.fieldLabel}>Price</Text>
              <View style={s.priceRow}>
                <Text style={s.dollar}>$</Text>
                <TextInput
                  style={[s.input, { flex: 1 }]}
                  value={ePrice}
                  onChangeText={setEPrice}
                  keyboardType="decimal-pad"
                  placeholder="0.00"
                  placeholderTextColor="#444"
                />
              </View>

              {/* Condition */}
              <Text style={s.fieldLabel}>Condition</Text>
              <View style={s.chipRow}>
                {GRADES.map(g => {
                  const color = COND_COLOR[g] || '#555';
                  const active = eCondition === g;
                  return (
                    <TouchableOpacity
                      key={g}
                      style={[s.chip, active && { borderColor: color, backgroundColor: color + '22' }]}
                      onPress={() => setECondition(g)}
                    >
                      <Text style={[s.chipText, active && { color }]}>{g}</Text>
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
                      {st.replace(/_/g, ' ')}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Section */}
              <Text style={s.fieldLabel}>Section</Text>
              <View style={s.chipRow}>
                {sections.map(loc => (
                  <TouchableOpacity
                    key={String(loc.location_id)}
                    style={[s.chip, eSection === loc.section && s.chipActive]}
                    onPress={() => setESection(loc.section)}
                  >
                    <Text style={[s.chipText, eSection === loc.section && s.chipTextActive]}>
                      {loc.section}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Toggles */}
              <View style={s.toggleRow}>
                <Text style={s.toggleLabel}>Signed</Text>
                <Switch value={eSigned} onValueChange={setESigned}
                  thumbColor={eSigned ? ACCENT : '#333'}
                  trackColor={{ false: '#222', true: '#4a1020' }} />
              </View>
              <View style={[s.toggleRow, s.toggleBorder]}>
                <Text style={s.toggleLabel}>Inscribed</Text>
                <Switch value={eInscribed} onValueChange={setEInscribed}
                  thumbColor={eInscribed ? ACCENT : '#333'}
                  trackColor={{ false: '#222', true: '#4a1020' }} />
              </View>

              {/* Actions */}
              <TouchableOpacity
                style={[s.saveBtn, saving && s.btnDisabled]}
                onPress={handleSave}
                disabled={saving}
              >
                {saving
                  ? <ActivityIndicator color="#fff" />
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
  container: { flex: 1, backgroundColor: BG },

  statsRow: {
    flexDirection: 'row', backgroundColor: '#0c0c17',
    paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#1a1a2a',
  },
  stat: { flex: 1, alignItems: 'center' },
  statBorder: { borderLeftWidth: 1, borderRightWidth: 1, borderColor: '#1a1a2a' },
  statNum: { color: '#fff', fontSize: 22, fontWeight: '700' },
  statLabel: { color: '#555', fontSize: 11, marginTop: 2, textTransform: 'uppercase', letterSpacing: 0.5 },

  searchRow: {
    flexDirection: 'row', paddingHorizontal: 12, paddingVertical: 10,
    borderBottomWidth: 1, borderBottomColor: '#1a1a2a', alignItems: 'center',
  },
  searchWrap: {
    flex: 1, flexDirection: 'row', alignItems: 'center',
    backgroundColor: '#1a1a2a', borderRadius: 10,
    paddingHorizontal: 10, borderWidth: 1, borderColor: '#252530',
  },
  searchIcon: { color: '#555', fontSize: 18, marginRight: 6 },
  searchInput: { flex: 1, paddingVertical: 9, color: '#fff', fontSize: 14 },
  clearBtn: { padding: 4 },
  clearBtnText: { color: '#555', fontSize: 13 },

  item: {
    flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 13,
    borderBottomWidth: 1, borderBottomColor: '#0f0f18', alignItems: 'center',
  },
  itemMain: { flex: 1, marginRight: 12 },
  itemTitle: { color: '#fff', fontSize: 14, fontWeight: '600' },
  itemAuthor: { color: '#666', fontSize: 12, marginTop: 2 },
  itemMeta: { flexDirection: 'row', gap: 8, marginTop: 3 },
  itemSku: { color: '#333', fontSize: 10, fontFamily: 'monospace' },
  itemSection: { color: '#2a2a4a', fontSize: 10 },
  itemRight: { alignItems: 'flex-end', gap: 6 },
  itemPrice: { color: ACCENT, fontSize: 16, fontWeight: '700' },
  condBadge: { borderWidth: 1, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  condBadgeText: { fontSize: 10, fontWeight: '600' },

  emptyContainer: { flex: 1 },
  emptyWrap: { alignItems: 'center', marginTop: 80 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyTitle: { color: '#fff', fontSize: 16, fontWeight: '600' },
  emptyHint: { color: '#555', fontSize: 13, marginTop: 6 },

  // Modal
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: '#0f0f1a', borderTopLeftRadius: 20, borderTopRightRadius: 20,
    maxHeight: '90%', borderTopWidth: 1, borderColor: '#1e1e2e',
  },
  modalContent: { padding: 20, paddingBottom: 40 },
  modalHeader: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 4 },
  modalTitle: { flex: 1, color: '#fff', fontSize: 17, fontWeight: '700', marginRight: 12 },
  modalClose: { padding: 4 },
  modalCloseText: { color: '#555', fontSize: 18 },
  modalSku: { color: '#333', fontSize: 11, fontFamily: 'monospace', marginBottom: 16 },

  fieldLabel: { color: '#555', fontSize: 12, marginTop: 16, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 },
  priceRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dollar: { color: '#555', fontSize: 18, fontWeight: '600' },
  input: {
    backgroundColor: '#1a1a2a', borderWidth: 1, borderColor: '#252535',
    borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, color: '#fff', fontSize: 14,
  },

  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16,
    borderWidth: 1, borderColor: '#252535', backgroundColor: CARD,
  },
  chipActive: { backgroundColor: '#1e0810', borderColor: ACCENT },
  chipText: { color: '#666', fontSize: 12 },
  chipTextActive: { color: '#fff', fontWeight: '600' },

  toggleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 12 },
  toggleBorder: { borderTopWidth: 1, borderTopColor: '#1a1a2a' },
  toggleLabel: { color: '#fff', fontSize: 15 },

  saveBtn: { backgroundColor: ACCENT, padding: 16, borderRadius: 12, alignItems: 'center', marginTop: 20 },
  saveBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  btnDisabled: { opacity: 0.5 },
  deleteBtn: { alignItems: 'center', padding: 14, marginTop: 8 },
  deleteBtnText: { color: '#e74c3c', fontSize: 14 },
});
