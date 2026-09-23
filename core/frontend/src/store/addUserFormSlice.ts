import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from './index';

interface AddUserFormState {
  email: string;
  username: string;
  password: string;
  confirmPassword: string;
}

const initialState: AddUserFormState = {
  email: '',
  username: '',
  password: '',
  confirmPassword: '',
};

const addUserFormSlice = createSlice({
  name: 'addUserForm',
  initialState,
  reducers: {
    setEmail: (state, action: PayloadAction<string>) => {
      state.email = action.payload;
    },
    setUsername: (state, action: PayloadAction<string>) => {
      state.username = action.payload;
    },
    setPassword: (state, action: PayloadAction<string>) => {
      state.password = action.payload;
    },
    setConfirmPassword: (state, action: PayloadAction<string>) => {
      state.confirmPassword = action.payload;
    },
    resetForm: () => initialState,
  },
});

export const {
  setEmail,
  setUsername,
  setPassword,
  setConfirmPassword,
  resetForm,
} = addUserFormSlice.actions;

// Selectors
export const selectAddUserForm = (state: RootState) => state.addUserForm;
export const selectEmail = (state: RootState) => state.addUserForm.email;
export const selectUsername = (state: RootState) => state.addUserForm.username;
export const selectPassword = (state: RootState) => state.addUserForm.password;
export const selectConfirmPassword = (state: RootState) => state.addUserForm.confirmPassword;

export default addUserFormSlice.reducer;
