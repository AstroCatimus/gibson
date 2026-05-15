/**
 * Gibson — Tab navigator layout.
 * Six tabs: Scan · Books · Sale · Review · Verify · Account
 */

import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Platform, View } from 'react-native';
import { C } from '../../src/lib/theme';

function TabIcon({ name, color, size, focused }) {
  return (
    <View style={{ alignItems: 'center', justifyContent: 'center' }}>
      <Ionicons name={name} color={color} size={focused ? size : size - 1} />
    </View>
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: C.surface },
        headerTintColor: C.text,
        headerTitleStyle: { fontWeight: '700', fontSize: 17, color: C.text },
        headerShadowVisible: false,
        headerTitleAlign: 'left',
        tabBarStyle: {
          backgroundColor: C.surface,
          borderTopColor: C.border,
          borderTopWidth: 1,
          height: Platform.OS === 'ios' ? 88 : 64,
          paddingBottom: Platform.OS === 'ios' ? 28 : 8,
          paddingTop: 8,
        },
        tabBarActiveTintColor: C.accent,
        tabBarInactiveTintColor: C.text3,
        tabBarLabelStyle: {
          fontSize: 10,
          fontWeight: '600',
          letterSpacing: 0.2,
          marginTop: 1,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Scan',
          headerShown: false,
          tabBarIcon: ({ color, size, focused }) => (
            <TabIcon name={focused ? 'scan' : 'scan-outline'} color={color} size={size} focused={focused} />
          ),
        }}
      />
      <Tabs.Screen
        name="inventory"
        options={{
          title: 'Books',
          headerTitle: 'Inventory',
          tabBarIcon: ({ color, size, focused }) => (
            <TabIcon name={focused ? 'library' : 'library-outline'} color={color} size={size} focused={focused} />
          ),
        }}
      />
      <Tabs.Screen
        name="pos"
        options={{
          title: 'Sale',
          headerTitle: 'Point of Sale',
          tabBarIcon: ({ color, size, focused }) => (
            <TabIcon name={focused ? 'receipt' : 'receipt-outline'} color={color} size={size} focused={focused} />
          ),
        }}
      />
      <Tabs.Screen
        name="research"
        options={{
          title: 'Review',
          headerTitle: 'Review Queue',
          tabBarIcon: ({ color, size, focused }) => (
            <TabIcon name={focused ? 'file-tray-full' : 'file-tray-full-outline'} color={color} size={size} focused={focused} />
          ),
        }}
      />
      <Tabs.Screen
        name="defrag"
        options={{
          title: 'Verify',
          headerTitle: 'Shelf Verification',
          tabBarIcon: ({ color, size, focused }) => (
            <TabIcon name={focused ? 'checkmark-done-circle' : 'checkmark-done-circle-outline'} color={color} size={size} focused={focused} />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Account',
          headerTitle: 'Account & Settings',
          tabBarIcon: ({ color, size, focused }) => (
            <TabIcon name={focused ? 'person-circle' : 'person-circle-outline'} color={color} size={size} focused={focused} />
          ),
        }}
      />
    </Tabs>
  );
}
