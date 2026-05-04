/**
 * Gibson — Condition Screen.
 * Tap mode for quick grading (<$15, first floor).
 * One tap per grade. No questions.
 */

import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';

const ACCENT = '#e94560';
const BG = '#0f0f1a';
const CARD = '#13131f';

const GRADES = [
  { grade: 'Fine',       desc: 'As new. No defects.',               color: '#2ecc71', dot: '#0d2a15' },
  { grade: 'Very Good+', desc: 'Minor shelf wear only.',             color: '#27ae60', dot: '#0d2218' },
  { grade: 'Very Good',  desc: 'Shows light use.',                   color: '#3498db', dot: '#0d1a2a' },
  { grade: 'Good+',      desc: 'Average used copy, small defects.',  color: '#9b59b6', dot: '#1a0d2a' },
  { grade: 'Good',       desc: 'Complete, heavy wear.',              color: '#f39c12', dot: '#2a1e0a' },
  { grade: 'Fair',       desc: 'Reading copy only.',                 color: '#e67e22', dot: '#2a1508' },
  { grade: 'Poor',       desc: 'Incomplete or heavily damaged.',     color: '#e74c3c', dot: '#2a0d0d' },
];

export default function ConditionScreen() {
  const params = useLocalSearchParams();
  const price = parseFloat(params.price || '0');

  function handleGrade(grade) {
    router.push({ pathname: '/catalogue', params: { ...params, condition: grade } });
  }

  return (
    <ScrollView style={s.container} contentContainerStyle={s.content}>

      {/* Book + price summary */}
      <View style={s.summary}>
        <Text style={s.summaryTitle} numberOfLines={2}>{params.title || 'Untitled'}</Text>
        <Text style={s.summaryPrice}>${price.toFixed(2)}</Text>
      </View>

      <Text style={s.sectionLabel}>Select Condition</Text>

      {GRADES.map((g) => (
        <TouchableOpacity
          key={g.grade}
          style={s.gradeBtn}
          onPress={() => handleGrade(g.grade)}
          activeOpacity={0.7}
        >
          <View style={[s.gradeIndicator, { backgroundColor: g.dot }]}>
            <View style={[s.gradeDot, { backgroundColor: g.color }]} />
          </View>
          <View style={s.gradeContent}>
            <Text style={s.gradeName}>{g.grade}</Text>
            <Text style={s.gradeDesc}>{g.desc}</Text>
          </View>
          <Text style={[s.gradeArrow, { color: g.color }]}>›</Text>
        </TouchableOpacity>
      ))}

    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  content: { padding: 16, paddingBottom: 40 },

  summary: {
    backgroundColor: CARD,
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#1e1e2e',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  summaryTitle: { flex: 1, color: '#fff', fontSize: 15, fontWeight: '600' },
  summaryPrice: { color: ACCENT, fontSize: 24, fontWeight: '800' },

  sectionLabel: {
    color: '#444', fontSize: 11,
    textTransform: 'uppercase', letterSpacing: 1,
    marginBottom: 10, paddingHorizontal: 2,
  },

  gradeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: CARD,
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#1e1e2e',
    gap: 12,
  },
  gradeIndicator: {
    width: 32, height: 32, borderRadius: 8,
    alignItems: 'center', justifyContent: 'center',
  },
  gradeDot: { width: 12, height: 12, borderRadius: 6 },
  gradeContent: { flex: 1 },
  gradeName: { color: '#fff', fontSize: 15, fontWeight: '700' },
  gradeDesc: { color: '#555', fontSize: 12, marginTop: 2 },
  gradeArrow: { fontSize: 22, fontWeight: '300' },
});
