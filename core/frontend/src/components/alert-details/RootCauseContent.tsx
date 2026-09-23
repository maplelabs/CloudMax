import { AlertCircle, Activity, TriangleAlert } from "lucide-react";
import { MarkdownContent } from "./MarkdownContent";

interface RootCauseContentProps {
  content?: string;
}

export const RootCauseContent = ({ content }: RootCauseContentProps) => {
  if (!content) {
    return <div className="text-secondary text-center py-4">No content available</div>;
  }

  // Split content by "## Conclusion" heading
  const conclusionMatch = content.match(/^## Conclusion\s*$/m);

  if (!conclusionMatch) {
    // If no conclusion section found, render normally
    return <MarkdownContent content={content} />;
  }

  // Split content into parts: before conclusion and conclusion section
  const conclusionIndex = conclusionMatch.index!;
  const beforeConclusion = content.substring(0, conclusionIndex).trim();
  const afterConclusion = content.substring(conclusionIndex).trim();

  // Extract the conclusion content
  const conclusionLines = afterConclusion.split('\n');
  let rootCauseTitle = '';
  let rootCauseText = '';
  let analysisTitle = '';
  let analysisText = '';
  let investigationStatusTitle = '';
  let investigationStatusText = '';
  let reasonTitle = '';
  let reasonText = '';

  let currentSection = '';

  for (let i = 1; i < conclusionLines.length; i++) {
    const line = conclusionLines[i];

    // Check if we hit another ## heading (end of conclusion section)
    if (line.trim().startsWith('## ') && i > 1) {
      break;
    }

    // Check for **Root Cause**: or **Analysis**: (when root cause is identified)
    if (line.trim().startsWith('**Root Cause**:')) {
      currentSection = 'rootCause';
      rootCauseTitle = 'Root Cause';
      rootCauseText = line.replace(/^\*\*Root Cause\*\*:\s*/, '').trim();
      continue;
    }

    if (line.trim().startsWith('**Analysis**:')) {
      currentSection = 'analysis';
      analysisTitle = 'Analysis';
      analysisText = line.replace(/^\*\*Analysis\*\*:\s*/, '').trim();
      continue;
    }

    // Check for **Investigation Status**: or **Reason**: (when root cause is NOT determined)
    if (line.trim().startsWith('**Investigation Status**:')) {
      currentSection = 'investigationStatus';
      investigationStatusTitle = 'Investigation Status';
      investigationStatusText = line.replace(/^\*\*Investigation Status\*\*:\s*/, '').trim();
      continue;
    }

    if (line.trim().startsWith('**Reason**:')) {
      currentSection = 'reason';
      reasonTitle = 'Reason';
      reasonText = line.replace(/^\*\*Reason\*\*:\s*/, '').trim();
      continue;
    }

    // Append to current section
    if (currentSection === 'rootCause' && line.trim() && !line.trim().startsWith('**')) {
      rootCauseText += ' ' + line.trim();
    } else if (currentSection === 'analysis' && line.trim() && !line.trim().startsWith('**')) {
      analysisText += ' ' + line.trim();
    } else if (currentSection === 'investigationStatus' && line.trim() && !line.trim().startsWith('**')) {
      investigationStatusText += ' ' + line.trim();
    } else if (currentSection === 'reason' && line.trim() && !line.trim().startsWith('**')) {
      reasonText += ' ' + line.trim();
    }
  }

  return (
    <div>
      {/* Render content before conclusion */}
      {beforeConclusion && <MarkdownContent content={beforeConclusion} />}

      {/* Conclusion Section with special styling */}
      <div className="mt-8 space-y-4">
        <h2 className="text-xl font-semibold mb-4 text-foreground">Conclusion</h2>

        {/* Root Cause Identified Scenario */}
        {rootCauseText && (
          <>
            {/* Root Cause Box - Red/Pink background */}
            <div className="border-l-4 border-danger bg-danger-light rounded-r-lg p-4">
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 mt-0.5">
                  <div className="w-6 h-6 rounded-full bg-danger flex items-center justify-center">
                    <TriangleAlert className="w-4 h-4 text-white" />
                  </div>
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-danger mb-2">{rootCauseTitle}</h3>
                  <p className="text-foreground leading-relaxed">{rootCauseText}</p>
                </div>
              </div>
            </div>

            {/* Analysis Box - Blue background */}
            {analysisText && (
              <div className="border-l-4 border-info bg-info-light rounded-r-lg p-4">
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 mt-0.5">
                    <div className="w-6 h-6 rounded-full bg-info flex items-center justify-center">
                      <AlertCircle className="w-4 h-4 text-white" />
                    </div>
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-info mb-2">{analysisTitle}</h3>
                    <p className="text-foreground leading-relaxed">{analysisText}</p>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {/* Root Cause Not Determined Scenario */}
        {investigationStatusText && (
          <>
            {/* Investigation Status Box - Warning/Yellow background */}
            <div className="border-l-4 border-warning bg-warning-light rounded-r-lg p-4">
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 mt-0.5">
                  <div className="w-6 h-6 rounded-full bg-warning flex items-center justify-center">
                    <AlertCircle className="w-4 h-4 text-white" />
                  </div>
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-warning mb-2">{investigationStatusTitle}</h3>
                  <p className="text-foreground leading-relaxed">{investigationStatusText}</p>
                </div>
              </div>
            </div>

            {/* Reason Box - Neutral/Gray background */}
            {reasonText && (
              <div className="border-l-4 border-secondary bg-surface-secondary rounded-r-lg p-4">
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 mt-0.5">
                    <div className="w-6 h-6 rounded-full bg-secondary flex items-center justify-center">
                      <Activity className="w-4 h-4 text-white" />
                    </div>
                  </div>
                  <div className="flex-1">
                    <h3 className="font-semibold text-secondary mb-2">{reasonTitle}</h3>
                    <p className="text-foreground leading-relaxed">{reasonText}</p>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};