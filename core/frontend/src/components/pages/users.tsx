import { useState, useMemo } from "react";
import { useSelector, useDispatch } from "react-redux";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from "../ui/table";
import { Card } from "../ui/card";
import { Search, Loader2, RefreshCw, UserPlus, Trash2, Shield, ShieldOff, Info, UserCircle, Key, AlertCircle } from "lucide-react";
import { cn } from "../ui/utils";
import { useUsers, useDeleteUser, useMakeAdmin, useRemoveAdmin, useAddUser, useResetUserPassword } from "../../hooks/useUsers";
import { UsersQueryParams, User } from "../../types/users";
import { toast } from "sonner";
import { getUserInfoFromToken } from "../../utils/jwt";
import {
  selectAddUserForm,
  setEmail,
  setUsername,
  setPassword,
  setConfirmPassword,
  resetForm
} from "../../store/addUserFormSlice";
import type { AppDispatch } from "../../store";
import { useDebounce } from "../../hooks/useDebounce";

export function Users() {
  const dispatch = useDispatch<AppDispatch>();

  const [searchTerm, setSearchTerm] = useState("");
  const [adminFilter, setAdminFilter] = useState<string>("all");
  const [currentPage, setCurrentPage] = useState(1);
  const [showAddUserDialog, setShowAddUserDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showInfoDialog, setShowInfoDialog] = useState(false);
  const [showResetPasswordDialog, setShowResetPasswordDialog] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const itemsPerPage = 10;

  // Debounce search term to reduce API calls while typing
  const debouncedSearchTerm = useDebounce(searchTerm, 500);

  // Add user form state from Redux
  const formState = useSelector(selectAddUserForm);
  const { email: newUserEmail, username: newUserUsername, password: newUserPassword, confirmPassword } = formState;

  // Get current user info
  const currentUserInfo = getUserInfoFromToken();
  const isCurrentUserAdmin = currentUserInfo?.admin || false;

  // Build query parameters
  const queryParams: UsersQueryParams = useMemo(() => {
    const params: UsersQueryParams = {
      page: currentPage,
      page_size: itemsPerPage,
    };

    if (debouncedSearchTerm.trim()) {
      params.search = debouncedSearchTerm.trim();
    }

    if (adminFilter !== "all") {
      params.is_admin = adminFilter === "admin";
    }

    return params;
  }, [currentPage, debouncedSearchTerm, adminFilter]);

  // Fetch users
  const { data, isLoading, error, refetch } = useUsers(queryParams);

  // Mutations
  const deleteUserMutation = useDeleteUser();
  const makeAdminMutation = useMakeAdmin();
  const removeAdminMutation = useRemoveAdmin();
  const addUserMutation = useAddUser();
  const resetPasswordMutation = useResetUserPassword();

  const handleRefresh = async() => {
    try{
      await refetch();
      error ? toast.error("Failed to refresh users list") : toast.success("Users list refreshed");
    }
    catch{
      toast.error("Failed to refresh users list");
    }
  };

  const handleSearch = (value: string) => {
    setSearchTerm(value);
    setCurrentPage(1);
  };

  const handleAdminFilterChange = (value: string) => {
    setAdminFilter(value);
    setCurrentPage(1);
  };

  const handleDeleteUser = async () => {
    if (!selectedUser) return;

    try {
      await deleteUserMutation.mutateAsync(selectedUser.id);
      toast.success(`User ${selectedUser.username} deleted successfully`);
      setShowDeleteDialog(false);
      setSelectedUser(null);
    } catch (error: any) {
      toast.error(error.message || "Failed to delete user");
    }
  };

  const handleMakeAdmin = async (user: User) => {
    try {
      await makeAdminMutation.mutateAsync(user.id);
      toast.success(`${user.username} is now an admin`);
    } catch (error: any) {
      toast.error(error.message || "Failed to make user admin");
    }
  };

  const handleRemoveAdmin = async (user: User) => {
    try {
      await removeAdminMutation.mutateAsync(user.id);
      toast.success(`Admin privileges removed from ${user.username}`);
    } catch (error: any) {
      toast.error(error.message || "Failed to remove admin privileges");
    }
  };

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();

    if (newUserPassword !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }

    if (newUserPassword.length < 8) {
      toast.error("Password must be at least 8 characters long");
      return;
    }

    try {
      await addUserMutation.mutateAsync({
        email: newUserEmail,
        username: newUserUsername,
        password: newUserPassword,
      });
      toast.success("User added successfully");
      setShowAddUserDialog(false);
      dispatch(resetForm());
    } catch (error: any) {
      toast.error(error.message || "Failed to add user");
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!selectedUser) return;

    if (newPassword !== confirmNewPassword) {
      toast.error("Passwords do not match");
      return;
    }

    if (newPassword.length < 8) {
      toast.error("Password must be at least 8 characters long");
      return;
    }

    try {
      await resetPasswordMutation.mutateAsync({
        userId: selectedUser.id,
        newPassword: newPassword,
      });
      toast.success(`Password reset successfully for ${selectedUser.username}`);
      setShowResetPasswordDialog(false);
      setSelectedUser(null);
      setNewPassword("");
      setConfirmNewPassword("");
    } catch (error: any) {
      toast.error(error.message || "Failed to reset password");
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  const formatDateTime = (dateString: string) => {
    return new Date(dateString).toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  // Calculate pagination from API response
  const totalPages = data ? Math.ceil(data.pagination.total_items / data.pagination.page_size) : 0;
  const totalCount = data ? data.pagination.total_items : 0;

  // Permission check
  if (!isCurrentUserAdmin) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <ShieldOff className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-lg font-medium">Access Denied</p>
          <p className="text-sm text-muted-foreground">You need admin privileges to access this page.</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
        <div className="p-6 space-y-6">
        <div className="flex justify-center w-full">
            <Card className="border border-border p-6 box-shadow w-full">
              <div className="flex flex-col items-center justify-center py-16 px-4">
            <AlertCircle className="h-12 w-12 text-danger" />
            <div className="text-center">
              <h3 className="text-lg font-semibold text-foreground">Failed to load users</h3>
              <p className="text-muted-foreground mb-4">
                {error instanceof Error ? error.message : 'Failed to load users'}
              </p>
              <Button onClick={() =>handleRefresh()} variant="outline">
                Try Again
              </Button>
            </div>
          </div>
            </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title font-bold title-lg-header">User Management</h1>
          <p className="text-muted-foreground">
            Manage system users, permissions, and access control

          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="lg"
            onClick={handleRefresh}
            disabled={isLoading}
            className="bg-white border border-border-medium text-muted-foreground"
          >
            <RefreshCw className={cn("h-4 w-4 mr-2", isLoading && "animate-spin")} />
            Refresh
          </Button>
          <Button
            size="lg"
            onClick={() => setShowAddUserDialog(true)}
            className="text-white active-range-bg"
          >
            <UserPlus className="h-4 w-4 mr-2" />
            Add User
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card className="p-4 box-shadow">
        <div className="flex justify-between items-center gap-4">

          <div className="flex relative flex-1 max-w-sm ">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
              <Input
                placeholder="Search by username or email..."
                value={searchTerm}
                onChange={(e) => handleSearch(e.target.value)}
                className="pl-10"
              />

            </div>
            <div className="p-1 text-muted-foreground px-2">
              {totalCount > 0 && ` ${totalCount} total user${totalCount !== 1 ? 's' : ''}`}
            </div>
          </div>
          <div className="md:w-48">
            <Select value={adminFilter} onValueChange={handleAdminFilterChange}>
              <SelectTrigger>
                <SelectValue placeholder="User Type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Users</SelectItem>
                <SelectItem value="admin">Admins Only</SelectItem>
                <SelectItem value="user">Regular Users</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </Card>

      {/* Users Table */}
      <Card className="overflow-hidden" style={{ boxShadow: '0px 4px 6px 2px #0000001A' }}>
        {isLoading ? (
          <div className="text-center py-8">
            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-loading" />
            <p className="text-secondary">Loading users...</p>
          </div>
        ) : !data || data.users.length === 0 ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center py-8">
              <UserCircle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-md font-medium">No users found</p>
              <p className="text-sm text-muted-foreground">Try adjusting your search or filters</p>
            </div>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/50 hover:bg-muted/50 border-b">
                    <TableHead className="table-header-text px-6">Username</TableHead>
                    <TableHead className="table-header-text px-6">Email</TableHead>
                    <TableHead className="table-header-text px-6">Role</TableHead>
                    <TableHead className="table-header-text px-6">Created</TableHead>
                    <TableHead className="table-header-text px-6 text-right">
                      <span className="flex justify-end">Actions</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.users.map((user, index) => {
                    const isCurrentUser = user.id.toString() === currentUserInfo?.sub;
                    return (
                      <TableRow
                        key={user.id}
                        className={cn(
                          "hover:bg-muted/50 hover:shadow-sm transition-all duration-200",
                          index !== data.users.length - 1 && "border-b border-border/50",
                          index % 2 === 0 ? "bg-background" : "bg-muted"
                        )}
                      >
                        <TableCell className="px-6 py-3">
                          <div className="flex items-center gap-2">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-9 w-9 rounded-full bg-gradient-green text-white transition-opacity"
                            >
                              <span className="text-sm font-semibold">{user?.username?.slice(0, 2)?.toUpperCase()}</span>
                            </Button>
                            <span className="table-data-text text-foreground">
                              {user.username}
                              {isCurrentUser && (
                                <span className="text-xs bg-success-light text-primary px-2 p-0.5 rounded" style={{marginLeft:2}}>You</span>
                              )}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="px-6 py-6 table-data-text text-muted-foreground">
                          <div className="flex items-center gap-2">
                            {/* <Mail className="h-4 w-4 text-muted-foreground" /> */}
                            {user.email}
                          </div>
                        </TableCell>
                        <TableCell className="px-6 py-6 table-data-text text-muted-foreground">
                          {user.admin ? (
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium ">Admin</span>
                            </div>
                          ) : (
                            <span className="text-sm text-muted-foreground">User</span>
                          )}
                        </TableCell>
                        <TableCell className="px-6 py-6 table-data-text text-muted-foreground">
                          <div className="flex items-center gap-2">
                            {/* <Calendar className="h-4 w-4" /> */}
                            {formatDate(user.created_at)}
                          </div>
                        </TableCell>
                        <TableCell className="px-6 text-right">
                          <TooltipProvider>
                            <div className="flex items-center gap-2 justify-end">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => {
                                      setSelectedUser(user);
                                      setShowInfoDialog(true);
                                    }}
                                    className="h-8 px-2"
                                  >
                                    <Info className="h-4 w-4 text-muted-foreground" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent className="text-white">
                                  <p>View user details</p>
                                </TooltipContent>
                              </Tooltip>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => {
                                      setSelectedUser(user);
                                      setShowResetPasswordDialog(true);
                                    }}
                                    disabled={resetPasswordMutation.isPending}
                                    className="h-8 px-2"
                                  >
                                    <Key className="h-4 w-4 text-muted-foreground" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent className="text-white">
                                  <p>Reset password</p>
                                </TooltipContent>
                              </Tooltip>
                              {!isCurrentUser && (
                                <>
                                  {user.admin ? (
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <Button
                                          variant="ghost"
                                          size="sm"
                                          onClick={() => handleRemoveAdmin(user)}
                                          disabled={removeAdminMutation.isPending}
                                          className="h-8 px-2"
                                        >
                                          <ShieldOff className="h-4 w-4 text-muted-foreground" />
                                        </Button>
                                      </TooltipTrigger>
                                      <TooltipContent className="text-white">
                                        <p>Remove admin privileges</p>
                                      </TooltipContent>
                                    </Tooltip>
                                  ) : (
                                    <Tooltip>
                                      <TooltipTrigger asChild>
                                        <Button
                                          variant="ghost"
                                          size="sm"
                                          onClick={() => handleMakeAdmin(user)}
                                          disabled={makeAdminMutation.isPending}
                                          className="h-8 px-2"
                                        >
                                          <Shield className="h-4 w-4 text-muted-foreground" />
                                        </Button>
                                      </TooltipTrigger>
                                      <TooltipContent className="text-white">
                                        <p>Make admin</p>
                                      </TooltipContent>
                                    </Tooltip>
                                  )}
                                  <Tooltip>
                                    <TooltipTrigger asChild>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => {
                                          setSelectedUser(user);
                                          setShowDeleteDialog(true);
                                        }}
                                        disabled={deleteUserMutation.isPending}
                                        className="h-8 px-2 text-danger hover:text-danger-dark hover:bg-danger-light disabled:opacity-50"
                                      >
                                        <Trash2 className="h-4 w-4 text-muted-foreground" />
                                      </Button>
                                    </TooltipTrigger>
                                    <TooltipContent className="text-white">
                                      <p>Delete user</p>
                                    </TooltipContent>
                                  </Tooltip>
                                </>
                              )}
                            </div>
                          </TooltipProvider>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex justify-between items-center px-6 py-4 bg-muted border-t" style={{ marginTop: -21 }}>
                <div className="text-sm">
                  <span className="text-muted-foreground">Showing</span> <span className="font-bold">{Math.min((currentPage - 1) * itemsPerPage + 1, totalCount)}-{Math.min(currentPage * itemsPerPage, totalCount)}</span> of <span className="font-bold">{totalCount}</span>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                    disabled={currentPage === 1}
                    className="table-pg-button text-muted-foreground"
                  >
                    Previous
                  </Button>

                  <div className="flex items-center gap-2">
                    {(() => {
                      const pages = [];
                      const delta = 2; // Number of pages to show around current page

                      // Always show first page
                      pages.push(
                        <Button
                          key={1}
                          variant={currentPage === 1 ? "default" : "outline"}
                          onClick={() => setCurrentPage(1)}
                          className={cn(
                            "table-pg-number-btn text-muted-foreground",
                            currentPage === 1
                              ? "bg-emerald-500 hover:bg-emerald-600 active-range-bg border-emerald-500"
                              : "hover:bg-muted"
                          )}
                        >
                          1
                        </Button>
                      );

                      // Show ellipsis if there's a gap after first page
                      if (currentPage > delta + 2) {
                        pages.push(
                          <span key="ellipsis-start" className="px-2 text-muted-foreground">
                            ...
                          </span>
                        );
                      }

                      // Show pages around current page
                      const startPage = Math.max(2, currentPage - delta);
                      const endPage = Math.min(totalPages - 1, currentPage + delta);

                      for (let i = startPage; i <= endPage; i++) {
                        pages.push(
                          <Button
                            key={i}
                            variant={currentPage === i ? "default" : "outline"}
                            onClick={() => setCurrentPage(i)}
                            className={cn(
                              "table-pg-number-btn text-muted-foreground",
                              currentPage === i
                                ? "bg-emerald-500 hover:bg-emerald-600 active-range-bg border-emerald-500"
                                : "hover:bg-muted"
                            )}
                          >
                            {i}
                          </Button>
                        );
                      }

                      // Show ellipsis if there's a gap before last page
                      if (currentPage < totalPages - delta - 1) {
                        pages.push(
                          <span key="ellipsis-end" className="px-2 text-muted-foreground">
                            ...
                          </span>
                        );
                      }

                      // Always show last page if more than 1 page
                      if (totalPages > 1) {
                        pages.push(
                          <Button
                            key={totalPages}
                            variant={currentPage === totalPages ? "default" : "outline"}
                            onClick={() => setCurrentPage(totalPages)}
                            className={cn(
                              "table-pg-number-btn text-muted-foreground",
                              currentPage === totalPages
                                ? "bg-emerald-500 hover:bg-emerald-600 active-range-bg border-emerald-500"
                                : "hover:bg-muted"
                            )}
                          >
                            {totalPages}
                          </Button>
                        );
                      }

                      return pages;
                    })()}
                  </div>

                  <Button
                    variant="outline"
                    onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                    disabled={currentPage === totalPages}
                    className="table-pg-button bg-card text-muted-foreground"
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </Card>

      {/* Add User Dialog */}
      <Dialog open={showAddUserDialog} onOpenChange={setShowAddUserDialog}>
        <DialogContent style={{width:500}}>
          <DialogHeader>
            <DialogTitle className="card-title">Add New User</DialogTitle>
            <DialogDescription>
              Create a new user account. The user will be able to log in with the provided credentials.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleAddUser} autoComplete="off">
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  placeholder="johndoe"
                  value={newUserUsername}
                  onChange={(e) => dispatch(setUsername(e.target.value))}
                  required
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="john.doe@example.com"
                  value={newUserEmail}
                  onChange={(e) => dispatch(setEmail(e.target.value))}
                  required
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="Min. 8 characters"
                  value={newUserPassword}
                  onChange={(e) => dispatch(setPassword(e.target.value))}
                  required
                  minLength={8}
                  autoComplete="new-password"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirmPassword">Confirm Password</Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  placeholder="Re-enter password"
                  value={confirmPassword}
                  onChange={(e) => dispatch(setConfirmPassword(e.target.value))}
                  required
                  minLength={8}
                  autoComplete="new-password"
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowAddUserDialog(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={addUserMutation.isPending} className="active-range-bg">
                {addUserMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Add User
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete User Alert Dialog */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="card-title">Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the user <strong>{selectedUser?.username}</strong> and all associated data.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteUser}
              className="bg-red-600 hover:bg-red-700 text-white"
            >
              {deleteUserMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Delete User
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* User Info Dialog */}
      <Dialog open={showInfoDialog} onOpenChange={setShowInfoDialog}>
        <DialogContent style={{width:500}}>
          <DialogHeader>
            <DialogTitle className="card-title">User Information</DialogTitle>
          </DialogHeader>
          {selectedUser && (
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label className="text-muted-foreground">Username</Label>
                <p className="text-sm font-medium">{selectedUser.username}</p>
              </div>
              <div className="space-y-2">
                <Label className="text-muted-foreground">Email</Label>
                <p className="text-sm font-medium">{selectedUser.email}</p>
              </div>
              <div className="space-y-2">
                <Label className="text-muted-foreground">User ID</Label>
                <p className="text-sm font-mono">{selectedUser.id}</p>
              </div>
              <div className="space-y-2">
                <Label className="text-muted-foreground">Role</Label>
                <p className="text-sm font-medium">
                  {selectedUser.admin ? (
                    <span className="text-success flex items-center gap-2">
                      <Shield className="h-4 w-4" />
                      Administrator
                    </span>
                  ) : (
                    "Regular User"
                  )}
                </p>
              </div>
              <div className="space-y-2">
                <Label className="text-muted-foreground">Created</Label>
                <p className="text-sm">{formatDateTime(selectedUser.created_at)}</p>
              </div>
              <div className="space-y-2">
                <Label className="text-muted-foreground">Last Updated</Label>
                <p className="text-sm">{formatDateTime(selectedUser.updated_at)}</p>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowInfoDialog(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset Password Dialog */}
      <Dialog open={showResetPasswordDialog} onOpenChange={setShowResetPasswordDialog}>
        <DialogContent style={{width:500}}>
          <DialogHeader>
            <DialogTitle className="card-title">Reset User Password</DialogTitle>
            <DialogDescription>
              Reset the password for <strong>{selectedUser?.username}</strong>. No old password validation is required for admin resets.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleResetPassword} autoComplete="off">
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="newPassword">New Password</Label>
                <Input
                  id="newPassword"
                  type="password"
                  placeholder="Min. 8 characters"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  minLength={8}
                  autoComplete="new-password"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirmNewPassword">Confirm New Password</Label>
                <Input
                  id="confirmNewPassword"
                  type="password"
                  placeholder="Re-enter new password"
                  value={confirmNewPassword}
                  onChange={(e) => setConfirmNewPassword(e.target.value)}
                  required
                  minLength={8}
                  autoComplete="new-password"
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setShowResetPasswordDialog(false);
                  setNewPassword("");
                  setConfirmNewPassword("");
                }}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={resetPasswordMutation.isPending} className="active-range-bg">
                {resetPasswordMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Reset Password
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
