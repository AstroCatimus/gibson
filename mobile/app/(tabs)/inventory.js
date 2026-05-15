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

export default function InventoryScreen() {
  const [items, setItems]         = useState([]);
  const [stats, setStats]         = useState(null);
  const [query, setQuery]         = useState('');
  const [loading, setLoading]     = useState(true);
  const [searching, setSearching] = useState(false);

  const [editing, setEditing]   = useState(null);
  const [sections, setSections] = useState([]);
  const [saving, setSaving]     = useState(false);

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
        asking_price:    ePrice ? parseFloat(ePrice) : null,
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
    const condColor = COND_COLOR[item.condition_grade] || C.text3;
    return (
      <TouchableOpacity style={s.item} onPress={() => openEdit(item)} activeOpacity={0.7}>
        {/* Condition stripe */}
        <View style={[s.condStripe, { backgroundColor: condColor }]} />
        <View style={s.itemBody}>
          <View style={s.itemMain}>
            <Text style={s.itemTitle} numberOfLines={1}>{item.title || 'Untitled'}</Text>
            <Text style={s.itemAuthor} numberOfLines={1}>{item.author || ''}</Text>
            <View style={s.itemMeta}>
              {item.gibson_sku ? (
                <Text style={s.itemSku}>{item.gibson_sku}</Text>
              ) : null}
              {item.section ? (
                <View style={s.sectionPill}>
                  <Text style={s.sectionPillText}>{item.section}</Text>
                </View>
              ) : null}
            </View>
          </View>
          <View style={s.itemRight}>
            <Text style={s.itemPrice}>
              {item.asking_price != null ? `$${item.asking_price.toFixed(2)}` : '—'}
            </Text>
            {item.condition_grade ? (
              <Text style={[s.condLabel, { color: condColor }]}>{item.condition_grade}</Text>
            ) : null}
          </View>
        </View>
      </TouchableOpacity>
    );
  }

  return (
    <View style={s.container}>

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
          <View style={s.stat}>
            <Text style={[s.statNum, { color: C.accent }]}>
              ${(stats.total_value || 0).toFixed(0)}
            </Text>
            <Text style={s.statLabel}>Value</Text>
          </View>
        </View>
      )}

      {/* ── Search ── */}
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

      {loading
        ? <ActivityIndicator color={C.accent} style={{ marginTop: 48 }} />
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

      {/* ── Edit modal ── */}
      <Modal visible={!!editing} animationType="slide" transparent onRequestClose={() => setEditing(null)}>
        <View style={s.modalOverlay}>
          <View style={s.modalSheet}>

            {/* Drag handle */}
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
                  placeholder="0.00"
                  placeholderTextColor={C.text3}
                />
              </View>

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

  // Stats
  statsRow: {
    flexDirection: 'row', backgroundColor: C.surface,
    paddingVertical: 16, borderBottomWidth: 1, borderBottomColor: C.border,
  },
  stat: { flex: 1, alignItems: 'center' },
  statDivider: { borderLeftWidth: 1, borderRightWidth: 1, borderColor: C.border },
  statNum: { color: C.text, fontSize: 22, fontWeight: '700' },
  statLabel: {
    color: C.text3, fontSize: 10, marginTop: 3,
    textTransform: 'uppercase', letterSpacing: 0.8,
  },

  // Search
  searchBar: {
    flexDirection: 'row', alignItems: 'center',
    margin: 12, paddingHorizontal: 12, paddingVertical: 10,
    backgroundColor: C.card, borderRadius: 10,
    borderWidth: 1, borderColor: C.border,
  },
  searchInput: { flex: 1, color: C.text, fontSize: 14 },
  clearBtn: { padding: 2 },

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
  itemMeta: { flexDirection: 'row', gap: 8, marginTop: 5, alignItems: 'center' },
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
  emptyHint: { color: C.text2, fontSize: 13, marginTop: 6 },

  // Modal
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
