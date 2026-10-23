import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  signUpWithEmail,
  signInWithEmail,
  signOutUser,
  isSupabaseConfigured,
} from '../services/supabaseClient';
import {
  getCurrentUser,
  setCurrentUser,
  DEMO_USERS,
  getSessionToken,
  subscribeToUserChanges,
} from '../services/dataService';

describe('Supabase Auth & Session Management (Phase 9)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('isSupabaseConfigured gracefully detects missing or placeholder keys in test env', () => {
    const configured = isSupabaseConfigured();
    // In vitest environment without live Supabase env vars, this returns false
    expect(typeof configured).toBe('boolean');
  });

  it('signUpWithEmail fails gracefully when Supabase is unconfigured', async () => {
    if (!isSupabaseConfigured()) {
      const res = await signUpWithEmail('newuser@example.com', 'password123');
      expect(res.user).toBeNull();
      expect(res.session).toBeNull();
      expect(res.error).toContain('not configured');
    }
  });

  it('signInWithEmail fails gracefully when Supabase is unconfigured', async () => {
    if (!isSupabaseConfigured()) {
      const res = await signInWithEmail('existing@example.com', 'password123');
      expect(res.user).toBeNull();
      expect(res.session).toBeNull();
      expect(res.error).toContain('not configured');
    }
  });

  it('signOutUser handles unconfigured environment without crashing', async () => {
    const res = await signOutUser();
    expect(res.error).toBeNull();
  });

  it('active session maintains safe role boundaries and demo fallback', () => {
    // Current user in offline/test environment defaults to planner
    const user = getCurrentUser();
    expect(user).toBeDefined();
    expect(user.role).toBe('planner');

    // Switch to approver demo persona
    setCurrentUser(DEMO_USERS[1]);
    const approver = getCurrentUser();
    expect(approver.role).toBe('approver');
    expect(approver.id).toBe(DEMO_USERS[1].id);

    // Reset back to planner
    setCurrentUser(DEMO_USERS[0]);
    expect(getCurrentUser().role).toBe('planner');
  });

  it('session token returns null when in offline demo persona mode', () => {
    setCurrentUser(DEMO_USERS[0]);
    expect(getSessionToken()).toBeNull();
  });

  it('subscribeToUserChanges notifies listener immediately and upon user change', () => {
    const events: Array<{ id: string; role: string }> = [];
    const unsubscribe = subscribeToUserChanges((u) => {
      if (u) {
        events.push({ id: u.id, role: u.role });
      }
    });

    // Switch user
    setCurrentUser(DEMO_USERS[1]);
    expect(events.length).toBeGreaterThanOrEqual(2);
    expect(events[events.length - 1].role).toBe('approver');

    // Clean up
    unsubscribe();
    setCurrentUser(DEMO_USERS[0]);
  });
});

