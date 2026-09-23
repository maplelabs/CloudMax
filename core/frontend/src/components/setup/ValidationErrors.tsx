import { XCircle } from "lucide-react";

interface ValidationErrorsProps {
  errors: string[];
}

export function ValidationErrors({ errors }: ValidationErrorsProps) {
  if (errors.length === 0) return null;

  return (
    <div data-validation-errors className="mt-6 p-4 bg-red-50 border border-red-200 rounded-lg">
      <div className="flex items-start gap-3">
        <XCircle className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
        <div className="flex-1">
          <h3 className="font-medium text-red-800 mb-2">Please fix the following errors before saving:</h3>
          <ul className="text-sm text-red-700 space-y-1">
            {errors.map((error, index) => (
              <li key={index} className="flex items-start gap-2">
                <span className="text-red-500 mt-1.5 w-1 h-1 bg-red-500 rounded-full flex-shrink-0"></span>
                <span>{error}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}