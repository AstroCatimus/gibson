/**
 * Gibson — POS Screen.
 * Counter flow: scan or type SKU/section+price, running total, close sale.
 */

import { useState } from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  FlatList, Alert, ActivityIndicator,
} from 'react-native';
import { api } from '../../src/lib/api';

const ACCENT = '#e94560';
const BG = '#0f0f1a';
const CARD = '#13131f';
const GREEN = '#2ecc71';

const TAX_RATE = 0.055; // Wisconsin 5.5%

export default function PosScreen() {
  const [skuInput, setSkuInput] = useState('');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saleComplete, setSaleComplete] = useState(null);

  const subtotal = items.reduce((sum, i) => sum + i.price, 0);
  const tax = subtotal * TAX_RATE;
  const total = subtotal + tax;

  async function handleAdd() {
    const input = skuInput.trim();
    if (!input) return;

    setLoading(true);
    try {
      let item;
      if (input.match(/^[A-Z]{2}-\d+/i)) {
        const result = await api.getItemBySku(input.toUpperCase());
        item = {
          stock_item_id: result.stock_item_id,
          title: result.title,
          sku: result.gibson_sku,
          price: result.asking_price,
          condition: result.condition_grade,
        };
      } else if (input.includes(' ')) {
        const parts = input.split(' ');
        const price = parseFloat(parts[parts.length - 1]);
        const section = parts.slice(0, -1).join(' ');
        if (!isNaN(price)) {
          item = { title: `${section}`, sku: null, price, condition: null };
        }
      } else {
        throw new Error('Enter a SKU (DL-1234) or "Section Price" (Fiction 12)');
      }

      if (item) {
        setItems(prev => [...prev, { ...item, id: Date.now() }]);
        setSkuInput('');
      }
    } catch (e) {
      Alert.alert('Not found', e.message);
    } finally {
      setLoading(false);
    }
  }

  function removeItem(id) {
    setItems(prev => prev.filter(i => i.id !== id));
  }

  async function closeSale(method) {
    if (!items.length) return;
    setLoading(true);
    try {
      const result = await api.createSale(
        items.map(i => ({
          stock_item_id: i.stock_item_id || null,
          realized_price: i.price,
        })),
        method
      );
      setSaleComplete({ total, method, saleId: result.sale_id });
      setItems([]);
    } catch (e) {
      Alert.alert('Sale error', e.message);
    } finally {
      setLoading(false);
    }
  }

  if (saleComplete) {
    return (
      <View style={s.doneScreen}>
        <View style={s.doneCheck}>
          <Text style={s.doneCheckText}>✓</Text>
        </View>
        <Text style={s.doneTitle}>Sale Complete</Text>
        <Text style={s.doneTotal}>${saleComplete.total.toFixed(2)}</Text>
        <Text style={s.doneMethod}>
          {saleComplete.method === 'cash' ? '💵 Cash' : '💳 Card'}
        </Text>
        {saleComplete.saleId && (
          <Text style={s.doneSaleId}>#{saleComplete.saleId}</Text>
        )}
        <TouchableOpacity style={s.newSaleBtn} onPress={() => setSaleComplete(null)}>
          <Text style={s.newSaleBtnText}>New Sale</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={s.container}>
      {/* Input row */}
      <View style={s.inputRow}>
        <TextInput
          style={s.skuInput}
          value={skuInput}
          onChangeText={setSkuInput}
          placeholder="SKU or Section + Price (Fiction 12)"
          placeholderTextColor="#444"
          autoCapitalize="characters"
          onSubmitEditing={handleAdd}
          returnKeyType="done"
        />
        <TouchableOpacity style={s.addBtn} onPress={handleAdd} disabled={loading}>
          {loading
            ? <ActivityIndicator color="#fff" size="small" />
            : <Text style={s.addBtnText}>Add</Text>
          }
        </TouchableOpacity>
      </View>

      {/* Item list */}
      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        style={{ flex: 1 }}
        contentContainerStyle={items.length === 0 ? s.emptyContainer : null}
        ListEmptyComponent={
          <View style={s.emptyWrap}>
            <Text style={s.emptyIcon}>🛒</Text>
            <Text style={s.emptyTitle}>Cart is empty</Text>
            <Text style={s.emptyHint}>Scan a SKU or enter "Section Price" above</Text>
          </View>
        }
        renderItem={({ item }) => (
          <View style={s.item}>
            <View style={{ flex: 1 }}>
              <Text style={s.itemTitle} numberOfLines={1}>{item.title}</Text>
              <View style={s.itemMeta}>
                <Text style={s.itemSku}>{item.sku || 'manual'}</Text>
                {item.condition && (
                  <Text style={s.itemCond}>{item.condition}</Text>
                )}
              </View>
            </View>
            <Text style={s.itemPrice}>${item.price.toFixed(2)}</Text>
            <TouchableOpacity onPress={() => removeItem(item.id)} style={s.removeBtn}>
              <Text style={s.removeText}>✕</Text>
            </TouchableOpacity>
          </View>
        )}
      />

      {/* Totals + close */}
      <View style={s.totals}>
        <View style={s.totalRow}>
          <Text style={s.totalLabel}>Subtotal</Text>
          <Text style={s.totalVal}>${subtotal.toFixed(2)}</Text>
        </View>
        <View style={s.totalRow}>
          <Text style={s.totalLabel}>Tax (5.5%)</Text>
          <Text style={s.totalVal}>${tax.toFixed(2)}</Text>
        </View>
        <View style={[s.totalRow, s.grandRow]}>
          <Text style={s.grandLabel}>Total</Text>
          <Text style={s.grandVal}>${total.toFixed(2)}</Text>
        </View>

        <View style={s.closeRow}>
          <TouchableOpacity
            style={[s.closeBtn, s.cashBtn, (!items.length || loading) && s.closeBtnDisabled]}
            onPress={() => closeSale('cash')}
            disabled={!items.length || loading}
          >
            <Text style={s.closeBtnIcon}>💵</Text>
            <Text style={s.closeBtnText}>Cash</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.closeBtn, s.cardBtn, (!items.length || loading) && s.closeBtnDisabled]}
            onPress={() => closeSale('card')}
            disabled={!items.length || loading}
          >
            <Text style={s.closeBtnIcon}>💳</Text>
            <Text style={s.closeBtnText}>Card</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },

  inputRow: {
    flexDirection: 'row',
    padding: 12,
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a2a',
  },
  skuInput: {
    flex: 1, backgroundColor: '#1a1a2a', borderWidth: 1, borderColor: '#252530',
    borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10,
    color: '#fff', fontSize: 14,
  },
  addBtn: {
    backgroundColor: ACCENT, paddingHorizontal: 18,
    borderRadius: 10, justifyContent: 'center',
  },
  addBtnText: { color: '#fff', fontWeight: '700', fontSize: 14 },

  emptyContainer: { flex: 1 },
  emptyWrap: { alignItems: 'center', marginTop: 60 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyTitle: { color: '#fff', fontSize: 16, fontWeight: '600' },
  emptyHint: { color: '#555', fontSize: 13, marginTop: 6, textAlign: 'center', paddingHorizontal: 40 },

  item: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 13,
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#0f0f18',
  },
  itemTitle: { color: '#fff', fontSize: 14, fontWeight: '600' },
  itemMeta: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 3 },
  itemSku: { color: '#444', fontSize: 11, fontFamily: 'monospace' },
  itemCond: { color: '#555', fontSize: 11 },
  itemPrice: { color: ACCENT, fontSize: 16, fontWeight: '700', marginRight: 14 },
  removeBtn: { padding: 6 },
  removeText: { color: '#444', fontSize: 16 },

  totals: {
    backgroundColor: CARD,
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 12,
    borderTopWidth: 1,
    borderTopColor: '#1a1a2a',
  },
  totalRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingVertical: 5,
  },
  totalLabel: { color: '#666', fontSize: 14 },
  totalVal: { color: '#aaa', fontSize: 14 },
  grandRow: {
    borderTopWidth: 1, borderTopColor: '#222',
    marginTop: 6, paddingTop: 10, marginBottom: 4,
  },
  grandLabel: { color: '#fff', fontSize: 18, fontWeight: '700' },
  grandVal: { color: GREEN, fontSize: 26, fontWeight: '800' },
  closeRow: { flexDirection: 'row', marginTop: 12, gap: 10 },
  closeBtn: {
    flex: 1, flexDirection: 'row',
    padding: 15, borderRadius: 12,
    alignItems: 'center', justifyContent: 'center', gap: 6,
  },
  cashBtn: { backgroundColor: '#1a3a1a', borderWidth: 1, borderColor: '#2ecc71' },
  cardBtn: { backgroundColor: '#1a1a3a', borderWidth: 1, borderColor: '#3498db' },
  closeBtnDisabled: { opacity: 0.35 },
  closeBtnIcon: { fontSize: 16 },
  closeBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },

  // Sale complete
  doneScreen: {
    flex: 1, backgroundColor: BG,
    alignItems: 'center', justifyContent: 'center', padding: 32,
  },
  doneCheck: {
    width: 80, height: 80, borderRadius: 40,
    backgroundColor: '#0d2d1a', borderWidth: 2, borderColor: GREEN,
    alignItems: 'center', justifyContent: 'center', marginBottom: 24,
  },
  doneCheckText: { color: GREEN, fontSize: 36, fontWeight: '700' },
  doneTitle: { color: '#fff', fontSize: 22, fontWeight: '700' },
  doneTotal: { color: GREEN, fontSize: 48, fontWeight: '800', marginTop: 8 },
  doneMethod: { color: '#888', fontSize: 16, marginTop: 6 },
  doneSaleId: { color: '#444', fontSize: 12, marginTop: 4, fontFamily: 'monospace' },
  newSaleBtn: {
    marginTop: 36, backgroundColor: ACCENT,
    paddingVertical: 14, paddingHorizontal: 48, borderRadius: 12,
  },
  newSaleBtnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
