import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { AlertCircle, Clock, RefreshCw } from "lucide-react";
import { MarkdownContent } from "../alert-details/MarkdownContent";

interface ScoreCriteria {
  title: string;
  description: string;
  score_percent: number;
}

interface Evaluation {
  average_score_percent: number;
  reason: string;
  score_criteria_cards: ScoreCriteria[];
}

interface GroupEvaluationTabProps {
  evaluation?: Evaluation | null;
  evaluationLoading?: boolean;
  evaluationStatus?: string;
}

export function GroupEvaluationTab({ evaluation, evaluationLoading, evaluationStatus }: GroupEvaluationTabProps) {
  // Check if evaluation is in progress
  const isInProgress = evaluationStatus === "processing" || evaluationStatus === "queued";
  const hasScores = evaluation && evaluation.score_criteria_cards?.length > 0;

  return (
    <div className="pb-6 space-y-6">
      {/* Evaluation Score Card */}
      <Card className="box-shadow rounded-lg mr-2">
        <CardContent className="p-6">
          {evaluationLoading ? (
            <div className="text-center py-16">
              <div className="max-w-md mx-auto">
                <div className="mb-4">
                  <div className="mx-auto w-12 h-12 bg-surface-secondary rounded-full flex items-center justify-center">
                    <Clock className="h-6 w-6 text-muted animate-spin" />
                  </div>
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">Loading Evaluation...</h3>
                <p className="text-secondary">
                  Please wait while we load the evaluation details.
                </p>
              </div>
            </div>
          ) : isInProgress ? (
            <div className="text-center py-16">
              <div className="max-w-md mx-auto">
                <div className="mb-4">
                  <div className="mx-auto w-12 h-12 bg-info-light rounded-full flex items-center justify-center">
                    <RefreshCw className="h-6 w-6 text-info animate-spin" />
                  </div>
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">Evaluation In Progress</h3>
                <p className="text-secondary">
                  Evaluation is currently {evaluationStatus === "queued" ? "queued" : "in progress"}. Please check back in a few minutes to see the results.
                </p>
              </div>
            </div>
          ) : hasScores ? (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 bg-success/10 rounded-lg flex items-center justify-center">
                  <svg width="46" height="46" viewBox="0 0 46 46" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <g filter="url(#filter0_dd_1099_22349)">
                      <rect x="3" y="2" width="40" height="40" rx="4" fill="#10B981" shapeRendering="crispEdges" />
                      <path d="M23 32C28.5228 32 33 27.5228 33 22C33 16.4772 28.5228 12 23 12C17.4772 12 13 16.4772 13 22C13 27.5228 17.4772 32 23 32Z" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M20 22L22 24L26 20" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </g>
                    <defs>
                      <filter id="filter0_dd_1099_22349" x="0" y="0" width="46" height="46" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
                        <feFlood floodOpacity="0" result="BackgroundImageFix" />
                        <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha" />
                        <feMorphology radius="1" operator="erode" in="SourceAlpha" result="effect1_dropShadow_1099_22349" />
                        <feOffset dy="1" />
                        <feGaussianBlur stdDeviation="1" />
                        <feComposite in2="hardAlpha" operator="out" />
                        <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.1 0" />
                        <feBlend mode="normal" in2="BackgroundImageFix" result="effect1_dropShadow_1099_22349" />
                        <feColorMatrix in="SourceAlpha" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0" result="hardAlpha" />
                        <feOffset dy="1" />
                        <feGaussianBlur stdDeviation="1.5" />
                        <feComposite in2="hardAlpha" operator="out" />
                        <feColorMatrix type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.1 0" />
                        <feBlend mode="normal" in2="effect1_dropShadow_1099_22349" result="effect2_dropShadow_1099_22349" />
                        <feBlend mode="normal" in="SourceGraphic" in2="effect2_dropShadow_1099_22349" result="shape" />
                      </filter>
                    </defs>
                  </svg>
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-foreground">Evaluation Score</h2>
                </div>
              </div>
              <div className="flex text-right justify-between">
                <div>
                  <div className="text-sm text-muted-foreground mb-1">Overall Score</div>
                  <div className="eval-tab-score" style={{ color: "#DD5E1E" }}>
                    {Math.round(evaluation.average_score_percent)}%
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-16">
              <div className="max-w-md mx-auto">
                <div className="mb-4">
                  <div className="mx-auto w-12 h-12 bg-surface-secondary rounded-full flex items-center justify-center">
                    <AlertCircle className="h-6 w-6 text-muted" />
                  </div>
                </div>
                <h3 className="text-lg font-medium text-foreground mb-2">No Evaluation Available</h3>
                <p className="text-secondary">
                  Please run evaluation on this alert group first.
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Score Breakdown Card */}
      {evaluation && evaluation.score_criteria_cards?.length > 0 && (
        <>
          <Card className="box-shadow rounded-lg mr-2 border">
            <CardContent className="p-0">
              <h3 className="text-xl font-bold text-foreground mb-6 p-6">Score Breakdown</h3>
              <div className="space-y-6">
                {evaluation.score_criteria_cards.map((criteria, index) => (
                  <div key={index}>
                    <div className="flex items-start justify-between mb-3 px-6">
                      <div className="flex-1 pr-6">
                        <h4 className="text-md font-semibold text-foreground mb-2">{criteria.title}</h4>
                        <p className="text-sm text-muted-foreground leading-relaxed">
                          {criteria.description}
                        </p>
                      </div>
                      <div className="flex flex-col items-end gap-2" style={{ minWidth: '120px' }}>
                        <div className="text-3xl font-bold text-foreground">{Math.round(criteria.score_percent)}%</div>
                        <div className="w-32 bg-gray-200 rounded-full h-2.5">
                          <div
                            className="bg-success h-2.5 rounded-full transition-all duration-300"
                            style={{ width: `${criteria.score_percent}%` }}
                          />
                        </div>
                      </div>
                    </div>
                    {index < evaluation.score_criteria_cards.length - 1 && (
                      <hr className="border-t border-gray-200 mt-6" />
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* Evaluation Summary Card */}
      {evaluation && evaluation.score_criteria_cards?.length > 0 && evaluation.reason && (
        <Card className="box-shadow rounded-lg mr-2">
          <CardHeader>
            <CardTitle className="title">Evaluation Summary</CardTitle>
          </CardHeader>
          <CardContent className="px-6">
            <div className="prose max-w-none">
              <MarkdownContent content={evaluation.reason} />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
