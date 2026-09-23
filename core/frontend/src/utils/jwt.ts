import { jwtDecode } from "jwt-decode";

export interface DecodedToken {
  sub: string; // user_id
  email: string;
  username: string;
  admin: boolean;
  exp: number;
  iat: number;
  type: string;
}

export function decodeJWT(token: string): DecodedToken | null {
  try {
    return jwtDecode<DecodedToken>(token);
  } catch (error) {
    console.error("Failed to decode JWT:", error);
    return null;
  }
}

export function getUserIdFromToken(): string | null {
  const token = localStorage.getItem("access_token");
  if (!token) {
    return null;
  }

  const decoded = decodeJWT(token);
  return decoded?.sub || null;
}

export function getUserInfoFromToken(): DecodedToken | null {
  const token = localStorage.getItem("access_token");
  if (!token) {
    return null;
  }

  return decodeJWT(token);
}

export function isTokenExpired(token: string): boolean {
  const decoded = decodeJWT(token);
  if (!decoded) {
    return true;
  }
  return decoded.exp * 1000 < Date.now();
}
