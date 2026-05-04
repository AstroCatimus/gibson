/**
 * Gibson — Pricing Screen.
 * Shows comps from BookFinder, BooksRun, Gibson POS.
 * Labeled SOLD / ASKING / TREND. Vialibri gate enforced.
 * Dealer sets final price before cataloguing.
 */

import { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, ActivityIndicator,
} from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import { api } from '../src/lib/api';

const ACCENT = '#e94560';
const BG = '#0f0f1a';
const CARD = '#13131f';
const GREEN = '#2ecc71';
const YELLOW = '#f39c12';
const BLUE = '#3498db';

const LABEL_STYLE = {
  SOLD:   { color: GREEN,  bg: '#0d2a15' },
  TREND:  { color: YELLOW, bg: '#2a1e0a' },
  ASKING: { color: BLUE,   bg: '#0d1a2a' },
};

function CompRow({ comp }) {
  const ls = LABEL_STYLE[comp.label] || { color: '#888', bg: '#1a1a2a' };
  return (
    <View style={s.compRow}>
      <View style={[s.compLabelBadge, { backgroundColor: ls.bg }]}>
        <Text style={[s.compLabelText, { color: ls.color }]}>{comp.label}</Text>
      </View>
      <Text style={s.compAmount}>${comp.amount?.toFixed(2)}</Text>
      <View style={s.compRight}>
        <Text style={s.compSource}>{comp.source}</Text>
        {comp.condition && <Text style={s.compCond}>{comp.condition}</Text>}
      </View>
    </View>
  );
}

export default function PricingScreen() {
  const params = useLocalSearchParams();
  const { isbn, title, author, year, editionId } = params;

  const [loading, setLoading] = useState(true);
  const [pricing, setPricing] = useState(null);
  const [dealerPrice, setDealerPrice] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => { loadPricing(); }, []);

  async function loadPricing() {
    setLoading(true);
    try {
      const result = await api.getPricing({
        isbn_13: isbn || null,
        title: title || null,
        author: author || null,
        edition_id: editionId || null,
      });
      setPricing(result);
      if (result.suggested_price) {
        setDealerPrice(String(result.suggested_price));
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleNext() {
    router.push({
      pathname: '/condition',
      params: { isbn, title, author, year, editionId, price: dealerPrice },
    });
  }

  const allComps = pricing
    ? [
        ...(pricing.gibson_pos || []),
        ...(pricing.vialibri || []),
        ...(pricing.ebay_sold || []),
        ...(pricing.ebay_active || []),
        ...(pricing.booksrun || []),
        ...(pricing.bookscouter || []),
      ]
    : [];

  return (
    <ScrollView style={s.container} contentContainerStyle={s.content}>

      {/* Book header */}
      <View style={s.card}>
        <Text style={s.bookTitle} numberOfLines={2}>{title || 'Untitled'}</Text>
        {author && (
          <Text style={s.bookAuthor}>{author}{year ? ` · ${year}` : ''}</Text>
        )}
        {isbn && <Text style={s.bookIsbn}>{isbn}</Text>}
      </View>

      {/* Loading */}
      {loading && (
        <View style={s.loadingCard}>
          <ActivityIndicator color={ACCENT} size="large" />
          <Text style={s.loadingText}>Fetching market data…</Text>
        </View>
      )}

      {/* Error */}
      {error && (
        <View style={[s.card, s.errorCard]}>
          <Text style={s.errorTitle}>⚠️  Pricing unavailable</Text>
          <Text style={s.errorText}>{error}</Text>
        </View>
      )}

      {pricing && !loading && (
        <>
          {/* No comps gate */}
          {!pricing.vialibri_has_comps && (
            <View style={[s.card, s.gateCard]}>
              <Text style={s.gateTitle}>No market comps found</Text>
              <Text style={s.gateText}>
                Nothing on BookFinder. Price for in-store only or queue for research before online listing.
              </Text>
            </View>
          )}

          {/* Suggested price — hero */}
          {pricing.suggested_price && (
            <View style={[s.card, s.suggestCard]}>
              <Text style={s.suggestLabel}>Gibson's Suggestion</Text>
              <Text style={s.suggestPrice}>${pricing.suggested_price.toFixed(2)}</Text>
              {pricing.price_range_low != null && (
                <Text style={s.rangeText}>
                  Market range: ${pricing.price_range_low.toFixed(2)} – ${pricing.price_range_high.toFixed(2)}
                </Text>
              )}
            </View>
          )}

          {/* Comps */}
          {allComps.length > 0 && (
            <View style={s.card}>
              <View style={s.compHeader}>
                <Text style={s.cardLabel}>Market Comparables</Text>
                <Text style={s.compCount}>{allComps.length} found</Text>
              </View>
              {allComps.map((comp, i) => <CompRow key={i} comp={comp} />)}
            </View>
          )}
        </>
      )}

      {/* Dealer price */}
      <View style={s.card}>
        <Text style={s.cardLabel}>Your Price</Text>
        <View style={s.priceInputRow}>
          <Text style={s.currencySymbol}>$</Text>
          <TextInput
            style={s.priceInput}
            value={dealerPrice}
            onChangeText={setDealerPrice}
            keyboardType="decimal-pad"
            placeholder="0.00"
            placeholderTextColor="#333"
          />
        </View>
      </View>

      <TouchableOpacity
        style={[s.primaryBtn, !dealerPrice && s.btnDisabled]}
        onPress={handleNext}
        disabled={!dealerPrice}
      >
        <Text style={s.primaryBtnText}>Set Condition →</Text>
      </TouchableOpacity>

    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  content: { padding: 16, paddingBottom: 40 },

  card: {
    backgroundColor: CARD,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#1e1e2e',
  },
  cardLabel: {
    color: '#444', fontSize: 11,
    textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10,
  },

  bookTitle: { color: '#fff', fontSize: 18, fontWeight: '700', lineHeight: 24 },
  bookAuthor: { color: '#888', fontSize: 13, marginTop: 4 },
  bookIsbn: { color: '#444', fontSize: 11, marginTop: 6, fontFamily: 'monospace' },

  loadingCard: {
    backgroundColor: CARD,
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#1e1e2e',
    gap: 12,
  },
  loadingText: { color: '#555', fontSize: 14 },

  errorCard: { borderColor: '#3a1515' },
  errorTitle: { color: '#e74c3c', fontWeight: '700', marginBottom: 6 },
  errorText: { color: '#888', fontSize: 13 },

  gateCard: { borderColor: YELLOW + '66', backgroundColor: '#1a140a' },
  gateTitle: { color: YELLOW, fontWeight: '700', marginBottom: 6 },
  gateText: { color: '#888', fontSize: 13, lineHeight: 20 },

  suggestCard: { borderColor: ACCENT + '55', backgroundColor: '#180810' },
  suggestLabel: { color: '#888', fontSize: 11, textTransform: 'uppercase', letterSpacing: 1 },
  suggestPrice: { fontSize: 48, fontWeight: '800', color: '#fff', marginTop: 4 },
  rangeText: { color: '#555', fontSize: 13, marginTop: 6 },

  compHeader: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: 4,
  },
  compCount: { color: '#444', fontSize: 12 },
  compRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingVertical: 9,
    borderBottomWidth: 1, borderBottomColor: '#111',
    gap: 10,
  },
  compLabelBadge: {
    width: 56, paddingVertical: 3,
    borderRadius: 5, alignItems: 'center',
  },
  compLabelText: { fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  compAmount: { flex: 1, color: '#fff', fontSize: 16, fontWeight: '700' },
  compRight: { alignItems: 'flex-end' },
  compSource: { color: '#555', fontSize: 11 },
  compCond: { color: '#333', fontSize: 10, marginTop: 1 },

  priceInputRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: '#1a1a2a', borderWidth: 1, borderColor: '#252535',
    borderRadius: 10, paddingHorizontal: 12, marginTop: 4,
  },
  currencySymbol: { color: '#888', fontSize: 28, fontWeight: '700', marginRight: 4 },
  priceInput: {
    flex: 1, color: '#fff', fontSize: 32,
    fontWeight: '800', paddingVertical: 12,
  },

  primaryBtn: {
    backgroundColor: ACCENT, padding: 16,
    borderRadius: 12, alignItems: 'center', marginBottom: 10,
  },
  primaryBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  btnDisabled: { opacity: 0.4 },
});
