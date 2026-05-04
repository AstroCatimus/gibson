/**
 * Gibson — Tab navigator layout.
 * Five tabs: Scan, Books, Sale, Research, Settings.
 */

import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Platform } from 'react-native';

const ACCENT = '#e94560';
const BG = '#0f0f1a';
const INACTIVE = '#444';
const TAB_BG = '#0c0c17';

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: BG },
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: '700', fontSize: 17 },
        headerShadowVisible: false,
        tabBarStyle: {
          backgroundColor: TAB_BG,
          borderTopColor: '#1a1a2a',
          borderTopWidth: 1,
          height: Platform.OS === 'ios' ? 84 : 64,
          paddingBottom: Platform.OS === 'ios' ? 24 : 8,
          paddingTop: 8,
        },
        tabBarActiveTintColor: ACCENT,
        tabBarInactiveTintColor: INACTIVE,
        tabBarLabelStyle: { fontSize: 10, fontWeight: '600', letterSpacing: 0.3 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Scan',
          headerShown: false,
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="camera-outline" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="inventory"
        options={{
          title: 'Books',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="library-outline" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="pos"
        options={{
          title: 'Sale',
          tabBarIcon: ({ color, size, focused }) => (
            <Ionicons name={focused ? 'cart' : 'cart-outline'} color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="research"
        options={{
          title: 'Research',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="flask-outline" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="defrag"
        options={{
          title: 'Defrag',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="checkmark-circle-outline" color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Settings',
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="person-circle-outline" color={color} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}
