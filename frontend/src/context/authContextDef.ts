import { createContext } from 'react';
import { AuthUser } from '../types';

export interface AuthContextType {
  user: AuthUser | null;
  sessionToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isConfigured: boolean;
  signIn: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
  signUp: (email: string, password: string) => Promise<{ success: boolean; error?: string; sessionCreated?: boolean }>;
  signOut: () => Promise<void>;
  selectDemoUser: (demoUser: AuthUser) => void;
  toggleDemoRole: () => void;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);
