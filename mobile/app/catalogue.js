/**
 * Gibson — Catalogue / Confirm Screen.
 * Final review before adding to inventory.
 * Section picker, signed/inscribed toggles, add button.
 */

import { useState, useRef, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, Switch, Alert, ActivityIndicator,
} from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import { api } from '../src/lib/api';

const ACCENT = '#e94560';
const BG = '#0f0f1a';
const CARD = '#13131f';
const GREEN = '#2ecc71';

export default function CatalogueScreen() {
  const params = useLocalSearchParams();

  const [title,     setTitle]     = useState(params.title     || '');
  const [author,    setAuthor]    = useState(params.author    || '');
  const [publisher]               = useState(params.publisher || '');
  const [price, setPrice]       = useState(params.price     || '');
  const [condition]             = useState(params.condition || 'Good');
  const [section, setSection]     = useState('');
  const [sections, setSections]   = useState([]);
  const [newSection, setNewSection] = useState('');
  const [addingSection, setAddingSection] = useState(false);
  const newSectionRef = useRef(null);
  const [signed, setSigned]       = useState(false);
  const [inscribed, setInscribed] = useState(false);
  const [loading, setLoading]   = useState(false);
  const [done, setDone]         = useState(false);

  useEffect(() => {
    api.getSections()
      .then(res => setSections(res.sections || []))
      .catch(() => setSections([]));
  }, []);

  function handleDeleteSection(loc) {
    Alert.alert(
      `Delete "${loc.section}"?`,
      loc.item_count > 0
        ? `${loc.item_count} book(s) are in this section. Move them first.`
        : 'This section will be removed.',
      loc.item_count > 0
        ? [{ text: 'OK' }]
        : [
            { text: 'Cancel', style: 'cancel' },
            {
              text: 'Delete', style: 'destructive',
              onPress: async () => {
                try {
                  await api.deleteSection(String(loc.location_id));
                  setSections(prev => prev.filter(s => s.location_id !== loc.location_id));
                  if (section === loc.section) setSection('');
                } catch (e) {
                  Alert.alert('Error', e.message);
                }
              },
            },
          ],
    );
  }

  async function handleAdd() {
    if (!title || !price || !section) {
      Alert.alert('Missing fields', 'Title, price, and section are required.');
      return;
    }

    setLoading(true);
    try {
      await api.confirmIdentification({
        title,
        author,
        publisher:        publisher || null,
        isbn_13:          params.isbn || null,
        publication_year: params.year ? parseInt(params.year) : null,
        edition_id:       params.editionId || null,
        asking_price:     parseFloat(price),
        condition_grade:  condition,
        section,
        is_signed:        signed,
        is_inscribed:     inscribed,
      });
      setDone(true);
    } catch (e) {
      Alert.alert('Error', e.message);
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <View style={s.doneScreen}>
        <View style={s.doneCircle}>
          <Text style={s.doneCheck}>✓</Text>
        </View>
        <Text style={s.doneTitle}>Added to Inventory</Text>
        <Text style={s.doneMeta}>{section} · {condition}</Text>
        <Text style={s.donePrice}>${parseFloat(price).toFixed(2)}</Text>
        <TouchableOpacity style={s.nextBtn} onPress={() => router.replace('/')}>
          <Text style={s.nextBtnText}>Scan Next Book</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.homeBtn} onPress={() => router.replace('/(tabs)')}>
          <Text style={s.homeBtnText}>Go to Home</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <ScrollView style={s.container} contentContainerStyle={s.content}>

      {/* Condition badge at top */}
      <View style={s.condRow}>
        <Text style={s.condLabel}>Condition</Text>
        <View style={s.condBadge}>
          <Text style={s.condBadgeText}>{condition}</Text>
        </View>
      </View>

      {/* Book details */}
      <View style={s.card}>
        <Text style={s.cardLabel}>Book Details</Text>

        <Text style={s.fieldLabel}>Title</Text>
        <TextInput
          style={s.input}
          value={title}
          onChangeText={setTitle}
          placeholder="Book title"
          placeholderTextColor="#444"
        />

        <Text style={s.fieldLabel}>Author</Text>
        <TextInput
          style={s.input}
          value={author}
          onChangeText={setAuthor}
          placeholder="Author name"
          placeholderTextColor="#444"
        />

        {publisher ? (
          <>
            <Text style={s.fieldLabel}>Publisher</Text>
            <Text style={s.publisherText}>{publisher}</Text>
          </>
        ) : null}

        <Text style={s.fieldLabel}>Price</Text>
        <View style={s.priceRow}>
          <Text style={s.dollar}>$</Text>
          <TextInput
            style={[s.input, s.priceInput]}
            value={price}
            onChangeText={setPrice}
            keyboardType="decimal-pad"
            placeholder="0.00"
            placeholderTextColor="#444"
          />
        </View>
      </View>

      {/* Section picker */}
      <Text style={s.sectionLabel}>Section {!section && <Text style={s.required}>*</Text>}</Text>
      <View style={s.sectionGrid}>
        {sections.map((loc) => {
          const active = section === loc.section;
          return (
            <TouchableOpacity
              key={String(loc.location_id)}
              style={[s.sectionBtn, active && s.sectionBtnActive]}
              onPress={() => { setSection(loc.section); setAddingSection(false); }}
              onLongPress={() => handleDeleteSection(loc)}
              delayLongPress={500}
            >
              {active && <Text style={s.sectionCheck}>✓ </Text>}
              <Text style={[s.sectionBtnText, active && s.sectionBtnTextActive]}>
                {loc.section}
              </Text>
            </TouchableOpacity>
          );
        })}
        <TouchableOpacity
          style={[s.sectionBtn, s.sectionBtnNew]}
          onPress={() => { setAddingSection(true); setTimeout(() => newSectionRef.current?.focus(), 50); }}
        >
          <Text style={s.sectionBtnNewText}>+ New</Text>
        </TouchableOpacity>
      </View>
      {addingSection && (
        <View style={s.newSectionRow}>
          <TextInput
            ref={newSectionRef}
            style={[s.input, { flex: 1 }]}
            value={newSection}
            onChangeText={setNewSection}
            placeholder="Section name…"
            placeholderTextColor="#444"
            returnKeyType="done"
            onSubmitEditing={() => {
              const name = newSection.trim();
              if (name) {
                setSection(name);
                if (!sections.find(s => s.section === name)) {
                  setSections(prev => [...prev, { location_id: `pending-${name}`, section: name, item_count: 0 }]);
                }
              }
              setAddingSection(false);
            }}
          />
          <TouchableOpacity
            style={s.newSectionAdd}
            onPress={() => {
              const name = newSection.trim();
              if (name) {
                setSection(name);
                if (!sections.find(s => s.section === name)) {
                  setSections(prev => [...prev, { location_id: `pending-${name}`, section: name, item_count: 0 }]);
                }
              }
              setAddingSection(false);
            }}
          >
            <Text style={s.newSectionAddText}>Add</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Toggles */}
      <View style={s.card}>
        <Text style={s.cardLabel}>Attributes</Text>
        <View style={s.toggleRow}>
          <View>
            <Text style={s.toggleLabel}>Signed</Text>
            <Text style={s.toggleHint}>Author or contributor signature</Text>
          </View>
          <Switch
            value={signed}
            onValueChange={setSigned}
            thumbColor={signed ? ACCENT : '#333'}
            trackColor={{ false: '#222', true: '#4a1020' }}
          />
        </View>
        <View style={[s.toggleRow, s.toggleBorder]}>
          <View>
            <Text style={s.toggleLabel}>Inscribed</Text>
            <Text style={s.toggleHint}>Personal dedication or note</Text>
          </View>
          <Switch
            value={inscribed}
            onValueChange={setInscribed}
            thumbColor={inscribed ? ACCENT : '#333'}
            trackColor={{ false: '#222', true: '#4a1020' }}
          />
        </View>
      </View>

      {/* Add button */}
      <TouchableOpacity
        style={[s.primaryBtn, (loading || !section) && s.btnDisabled]}
        onPress={handleAdd}
        disabled={loading || !section}
      >
        {loading
          ? <ActivityIndicator color="#fff" />
          : <Text style={s.primaryBtnText}>Add to Inventory</Text>
        }
      </TouchableOpacity>

    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  content: { padding: 16, paddingBottom: 40 },

  condRow: {
    flexDirection: 'row', alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 14,
  },
  condLabel: { color: '#555', fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.5 },
  condBadge: {
    borderWidth: 1, borderColor: '#3498db',
    borderRadius: 6, paddingHorizontal: 10, paddingVertical: 4,
    backgroundColor: '#0d1a2a',
  },
  condBadgeText: { color: '#3498db', fontSize: 12, fontWeight: '700' },

  card: {
    backgroundColor: CARD,
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#1e1e2e',
  },
  cardLabel: {
    color: '#444', fontSize: 11,
    textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4,
  },

  fieldLabel: { color: '#555', fontSize: 12, marginTop: 12, marginBottom: 4 },
  publisherText: { color: '#888', fontSize: 14, paddingVertical: 4 },
  input: {
    backgroundColor: '#1a1a2a',
    borderWidth: 1, borderColor: '#252535',
    borderRadius: 8,
    paddingHorizontal: 12, paddingVertical: 10,
    color: '#fff', fontSize: 14,
  },
  priceRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  priceInput: { flex: 1 },
  dollar: { color: '#555', fontSize: 18, fontWeight: '600' },

  sectionLabel: {
    color: '#444', fontSize: 11,
    textTransform: 'uppercase', letterSpacing: 1,
    marginBottom: 10, paddingHorizontal: 2,
  },
  required: { color: ACCENT },
  sectionGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  sectionBtn: {
    flexDirection: 'row',
    paddingHorizontal: 14, paddingVertical: 8,
    borderRadius: 20, borderWidth: 1,
    borderColor: '#252535', backgroundColor: CARD,
  },
  sectionBtnActive: { backgroundColor: '#1e0810', borderColor: ACCENT },
  sectionCheck: { color: ACCENT, fontSize: 13, fontWeight: '700' },
  sectionBtnText: { color: '#666', fontSize: 13 },
  sectionBtnTextActive: { color: '#fff', fontWeight: '600' },
  sectionBtnNew: { borderColor: '#2a2a3a', borderStyle: 'dashed' },
  sectionBtnNewText: { color: '#555', fontSize: 13 },
  newSectionRow: { flexDirection: 'row', gap: 8, marginBottom: 16, marginTop: -8 },
  newSectionAdd: {
    backgroundColor: ACCENT, borderRadius: 8,
    paddingHorizontal: 16, justifyContent: 'center',
  },
  newSectionAddText: { color: '#fff', fontWeight: '700', fontSize: 14 },

  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
  },
  toggleBorder: { borderTopWidth: 1, borderTopColor: '#1a1a2a' },
  toggleLabel: { color: '#fff', fontSize: 15, fontWeight: '600' },
  toggleHint: { color: '#555', fontSize: 11, marginTop: 2 },

  primaryBtn: {
    backgroundColor: ACCENT, padding: 16,
    borderRadius: 12, alignItems: 'center', marginBottom: 10,
  },
  primaryBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  btnDisabled: { opacity: 0.4 },

  // Done screen
  doneScreen: {
    flex: 1, backgroundColor: BG,
    alignItems: 'center', justifyContent: 'center', padding: 32,
  },
  doneCircle: {
    width: 80, height: 80, borderRadius: 40,
    backgroundColor: '#0d2a15', borderWidth: 2, borderColor: GREEN,
    alignItems: 'center', justifyContent: 'center', marginBottom: 24,
  },
  doneCheck: { color: GREEN, fontSize: 36, fontWeight: '700' },
  doneTitle: { color: '#fff', fontSize: 22, fontWeight: '700' },
  doneMeta: { color: '#555', fontSize: 14, marginTop: 8 },
  donePrice: { color: GREEN, fontSize: 36, fontWeight: '800', marginTop: 4, marginBottom: 32 },
  nextBtn: {
    backgroundColor: ACCENT,
    paddingVertical: 14, paddingHorizontal: 48, borderRadius: 12,
    marginBottom: 12,
  },
  nextBtnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  homeBtn: { paddingVertical: 10 },
  homeBtnText: { color: '#555', fontSize: 14 },
});
