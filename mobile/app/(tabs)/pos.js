/**
 * Gibson — POS Screen.
 * Counter flow: scan or type SKU/section+price, running total, close sale.
 */

import { useState } from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  FlatList, Alert, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../../src/lib/api';
import { C } from '../../src/lib/theme';

const TAX_RATE = 0.055; // Wisconsin 5.5%

export default function PosScreen() {
  const [skuInput, setSkuInput]       = useState('');
  const [items, setItems]             = useState([]);
  const [loading, setLoading]         = useState(false);
  const [saleComplete, setSaleComplete] = useState(null);

  const subtotal = items.reduce((sum, i) => sum + i.price, 0);
  const tax      = subtotal * TAX_RATE;
  const total    = subtotal + tax;

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
          title:     result.title,
          sku:       result.gibson_sku,
          price:     result.asking_price,
          condition: result.condition_grade,
        };
      } else if (input.includes(' ')) {
        const parts  = input.split(' ');
        const price  = parseFloat(parts[parts.length - 1]);
        const section = parts.slice(0, -1).join(' ');
        if (!isNaN(price)) {
          item = { title: section, sku: null, price, condition: null };
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
        items.map(i => ({ stock_item_id: i.stock_item_id || null, realized_price: i.price })),
        method,
      );
      setSaleComplete({ total, method, saleId: result.sale_id });
      setItems([]);
    } catch (e) {
      Alert.alert('Sale error', e.message);
    } finally {
      setLoading(false);
    }
  }

  // ── Sale complete screen ─────────────────────────────────────────
  if (saleComplete) {
    return (
      <View style={s.doneScreen}>
        <View style={s.doneCircle}>
          <Ionicons name="checkmark" size={44} color={C.green} />
        </View>
        <Text style={s.doneTitle}>Sale Complete</Text>
        <Text style={s.doneTotal}>${saleComplete.total.toFixed(2)}</Text>
        <View style={s.doneMethodRow}>
          <Ionicons
            name={saleComplete.method === 'cash' ? 'cash-outline' : 'card-outline'}
            size={18} color={C.text2}
          />
          <Text style={s.doneMethod}>
            {saleComplete.method === 'cash' ? 'Cash' : 'Card'}
          </Text>
        </View>
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

      {/* ── Input row ── */}
      <View style={s.inputRow}>
        <TextInput
          style={s.skuInput}
          value={skuInput}
          onChangeText={setSkuInput}
          placeholder="SKU  or  Section + Price (Fiction 12)"
          placeholderTextColor={C.text3}
          autoCapitalize="characters"
          onSubmitEditing={handleAdd}
          returnKeyType="done"
        />
        <TouchableOpacity style={[s.addBtn, loading && s.addBtnDisabled]} onPress={handleAdd} disabled={loading}>
          {loading
            ? <ActivityIndicator color={C.bg} size="small" />
            : <Text style={s.addBtnText}>Add</Text>
          }
        </TouchableOpacity>
      </View>

      {/* ── Cart ── */}
      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        style={{ flex: 1 }}
        contentContainerStyle={items.length === 0 ? s.emptyContainer : { paddingTop: 4 }}
        ListEmptyComponent={
          <View style={s.emptyWrap}>
            <Text style={s.emptyIcon}>🛒</Text>
            <Text style={s.emptyTitle}>Cart is empty</Text>
            <Text style={s.emptyHint}>Scan a SKU or enter "Section Price" above</Text>
          </View>
        }
        renderItem={({ item }) => (
          <View style={s.cartItem}>
            <View style={{ flex: 1 }}>
              <Text style={s.cartItemTitle} numberOfLines={1}>{item.title}</Text>
              <View style={s.cartItemMeta}>
                {item.sku
                  ? <Text style={s.cartSku}>{item.sku}</Text>
                  : <Text style={s.cartManual}>manual</Text>
                }
                {item.condition && (
                  <Text style={s.cartCond}>{item.condition}</Text>
                )}
              </View>
            </View>
            <Text style={s.cartPrice}>${item.price.toFixed(2)}</Text>
            <TouchableOpacity onPress={() => removeItem(item.id)} style={s.removeBtn} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Ionicons name="close-circle-outline" size={20} color={C.text3} />
            </TouchableOpacity>
          </View>
        )}
      />

      {/* ── Totals & close ── */}
      <View style={s.footer}>
        <View style={s.totalsBlock}>
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
        </View>

        <View style={s.payRow}>
          <TouchableOpacity
            style={[s.payBtn, s.cashBtn, (!items.length || loading) && s.payBtnDisabled]}
            onPress={() => closeSale('cash')}
            disabled={!items.length || loading}
          >
            <Ionicons name="cash-outline" size={20} color={C.green} />
            <Text style={[s.payBtnText, { color: C.green }]}>Cash</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.payBtn, s.cardBtn, (!items.length || loading) && s.payBtnDisabled]}
            onPress={() => closeSale('card')}
            disabled={!items.length || loading}
          >
            <Ionicons name="card-outline" size={20} color={C.blue} />
            <Text style={[s.payBtnText, { color: C.blue }]}>Card</Text>
          </TouchableOpacity>
        </View>
      </View>

    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },

  // Input row
  inputRow: {
    flexDirection: 'row', gap: 8,
    padding: 12, borderBottomWidth: 1, borderBottomColor: C.border,
    backgroundColor: C.surface,
  },
  skuInput: {
    flex: 1, backgroundColor: C.card, borderWidth: 1, borderColor: C.border,
    borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10,
    color: C.text, fontSize: 14,
  },
  addBtn: {
    backgroundColor: C.accent, paddingHorizontal: 20,
    borderRadius: 10, justifyContent: 'center', alignItems: 'center',
  },
  addBtnDisabled: { opacity: 0.5 },
  addBtnText: { color: C.bg, fontWeight: '700', fontSize: 14 },

  // Empty state
  emptyContainer: { flex: 1 },
  emptyWrap: { alignItems: 'center', marginTop: 64 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyTitle: { color: C.text, fontSize: 16, fontWeight: '600' },
  emptyHint: { color: C.text2, fontSize: 13, marginTop: 6, textAlign: 'center', paddingHorizontal: 40 },

  // Cart items
  cartItem: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: C.border,
  },
  cartItemTitle: { color: C.text, fontSize: 14, fontWeight: '500' },
  cartItemMeta: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 3 },
  cartSku:    { color: C.text3, fontSize: 11, fontFamily: 'monospace' },
  cartManual: { color: C.text3, fontSize: 11, fontStyle: 'italic' },
  cartCond:   { color: C.text2, fontSize: 11 },
  cartPrice:  { color: C.accent, fontSize: 16, fontWeight: '700', marginHorizontal: 14 },
  removeBtn:  { padding: 2 },

  // Footer
  footer: {
    backgroundColor: C.surface, borderTopWidth: 1, borderTopColor: C.border,
    paddingTop: 14, paddingHorizontal: 16, paddingBottom: 16,
  },
  totalsBlock: { marginBottom: 14 },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  totalLabel: { color: C.text2, fontSize: 14 },
  totalVal:   { color: C.text2, fontSize: 14 },
  grandRow: {
    borderTopWidth: 1, borderTopColor: C.border,
    marginTop: 6, paddingTop: 10,
  },
  grandLabel: { color: C.text, fontSize: 18, fontWeight: '700' },
  grandVal:   { color: C.green, fontSize: 26, fontWeight: '800' },

  // Pay buttons
  payRow: { flexDirection: 'row', gap: 10 },
  payBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 8, padding: 15, borderRadius: 12, borderWidth: 1,
  },
  cashBtn: { backgroundColor: C.greenBg, borderColor: C.green },
  cardBtn: { backgroundColor: C.blueBg,  borderColor: C.blue },
  payBtnDisabled: { opacity: 0.35 },
  payBtnText: { fontWeight: '700', fontSize: 15 },

  // Sale complete
  doneScreen: {
    flex: 1, backgroundColor: C.bg,
    alignItems: 'center', justifyContent: 'center', padding: 32,
  },
  doneCircle: {
    width: 88, height: 88, borderRadius: 44,
    backgroundColor: C.greenBg, borderWidth: 2, borderColor: C.green,
    alignItems: 'center', justifyContent: 'center', marginBottom: 24,
  },
  doneTitle:     { color: C.text, fontSize: 22, fontWeight: '700' },
  doneTotal:     { color: C.green, fontSize: 52, fontWeight: '800', marginTop: 6 },
  doneMethodRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8 },
  doneMethod:    { color: C.text2, fontSize: 15 },
  doneSaleId:    { color: C.text3, fontSize: 11, marginTop: 6, fontFamily: 'monospace' },
  newSaleBtn: {
    marginTop: 36, backgroundColor: C.accent,
    paddingVertical: 14, paddingHorizontal: 48, borderRadius: 12,
  },
  newSaleBtnText: { color: C.bg, fontWeight: '700', fontSize: 16 },
});
