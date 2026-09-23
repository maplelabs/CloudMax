import { configureStore, createSlice } from '@reduxjs/toolkit';
import logger from 'redux-logger';
import addUserFormReducer from './addUserFormSlice';

// Temporary dummy slice until you add real reducers
const dummySlice = createSlice({
  name: 'dummy',
  initialState: {},
  reducers: {}
});

export const store = configureStore({
  reducer: {
    dummy: dummySlice.reducer,
    addUserForm: addUserFormReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: ['persist/PERSIST'],
      },
    }).concat(logger),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;