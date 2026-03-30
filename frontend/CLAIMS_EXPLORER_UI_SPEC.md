"""Claims Explorer Card — Advanced Evidence Visualization UI

Specification for displaying evidence network state from next-generation extraction.
Focuses on evidence clusters rather than per-paper claims.
Emphasizes gap detection, contradiction mapping, and uncertainty decomposition.
"""

import json


CLAIMS_EXPLORER_SPECIFICATION = {
    
    "component_name": "ClaimsExplorerCard",
    
    "purpose": """
    Display the current state of evidence clusters (grouped by 
    intervention_canonical + outcome_canonical). Alert the mission
    operator to gaps, contradictions, and confidence patterns.
    
    NOT a citation manager view. This is an evidence graph view.
    """,
    
    "data_model": {
        "clusters": [
            {
                "cluster_id": "intervention|outcome",
                "intervention": "Drug X",
                "outcome": "Blood Pressure",
                
                "claim_count": 42,
                "direction_distribution": {
                    "positive": 28,
                    "negative": 8,
                    "null": 6,
                    "total": 42
                },
                
                "composite_confidence": 0.76,
                "confidence_weighted_average": 0.74,
                
                "contradictions": {
                    "count": 3,
                    "involves_claims": ["claim_id_1", "claim_id_2", "claim_id_3"],
                    "most_severe_delta": 0.45  # confidence difference
                },
                
                "replications": {
                    "count": 12,
                    "high_confidence_replications": 7
                },
                
                "evidence_gaps": [
                    {
                        "type": "NULL_RESULT_UNDERREPRESENTED",
                        "severity": "HIGH",  # Based on support_ratio
                        "suggestion_query": "[Drug X] no effect null result [BP reduction]"
                    },
                    {
                        "type": "HIGH_QUALITY_STUDY_ABSENT",
                        "severity": "HIGH",
                        "suggestion_query": "[Drug X] randomized controlled trial meta-analysis [BP]"
                    }
                ],
                
                "paper_count": 18,
                "last_updated": "2024-01-15T14:32:00Z"
            }
        ],
        
        "sorting_options": ["confidence", "claim_count", "gap_count", "contradiction_count"],
        "current_sort": "confidence"
    },
    
    
    "PRIMARY_VIEW_LAYOUT": {
        
        "header": {
            "title": "Evidence Clusters",
            "subtitle": "Mission: {{mission_name}}",
            "filter_controls": [
                {
                    "name": "minimum_confidence",
                    "type": "slider",
                    "min": 0.0,
                    "max": 1.0,
                    "default": 0.3,
                    "label": "Min Composite Confidence"
                },
                {
                    "name": "hide_isolated",
                    "type": "checkbox",
                    "default": False,
                    "label": "Hide isolated clusters (no contradictions or replications)"
                },
                {
                    "name": "show_gaps_only",
                    "type": "checkbox",
                    "default": False,
                    "label": "Show clusters with detection gaps only"
                },
                {
                    "name": "evidence_quality_filter",
                    "type": "multi-select",
                    "options": ["HIGH_QUALITY", "MODERATE", "LOW_QUALITY"],
                    "default": ["HIGH_QUALITY", "MODERATE"],
                    "label": "Study quality"
                }
            ]
        },
        
        "cluster_row": {
            
            "left_section": {
                "label_area": {
                    "intervention": "{{cluster.intervention}} → {{cluster.outcome}}",
                    "font_size": "16px",
                    "font_weight": "600",
                    "color": "#1f2937"
                },
                
                "metadata_line": {
                    "elements": [
                        {
                            "type": "badge",
                            "text": "{{cluster.claim_count}} claims",
                            "bg": "#e0e7ff",
                            "text_color": "#4c1d95"
                        },
                        {
                            "type": "badge",
                            "text": "{{cluster.paper_count}} papers",
                            "bg": "#dbeafe",
                            "text_color": "#0c2340"
                        },
                        {
                            "type": "timestamp",
                            "text": "Updated {{time_since(cluster.last_updated)}}",
                            "text_color": "#6b7280"
                        }
                    ]
                }
            },
            
            "direction_bar": {
                "type": "horizontal_stacked_bar",
                "width": "180px",
                "height": "24px",
                "segments": [
                    {
                        "name": "supporting",
                        "value": "{{cluster.direction_distribution.positive + cluster.direction_distribution.negative}}",
                        "percentage": "{{(supporting_count / total) * 100}}",
                        "color": "#10b981",  # Green
                        "icon": "↑↓",
                        "on_hover": "Positive/Negative direction claims"
                    },
                    {
                        "name": "contradicting",
                        "value": "{{cluster.direction_distribution.count_contradicting}}",
                        "percentage": "{{(contradicting / total) * 100}}",
                        "color": "#ef4444",  # Red
                        "icon": "⚔️",
                        "on_hover": "Contradicting claims detected"
                    },
                    {
                        "name": "null",
                        "value": "{{cluster.direction_distribution.null}}",
                        "percentage": "{{(null / total) * 100}}",
                        "color": "#d1d5db",  # Gray
                        "icon": "∅",
                        "on_hover": "No significant effect (null results)"
                    }
                ],
                "label_position": "below",
                "show_percentages": True
            },
            
            "confidence_display": {
                "composite": {
                    "type": "circular_progress",
                    "size": "56px",
                    "value": "{{cluster.composite_confidence}}",
                    "color": "dynamic",  # Color based on value
                    "color_rules": [
                        {"min": 0.75, "max": 1.0, "color": "#059669"},  # Dark green
                        {"min": 0.50, "max": 0.75, "color": "#f59e0b"},  # Amber
                        {"min": 0.0, "max": 0.50, "color": "#dc2626"}   # Red
                    ],
                    "label": "Confidence",
                    "on_hover": "Composite confidence: {{composite}}. Click for uncertainty breakdown."
                }
            },
            
            "gap_icons": {
                "layout": "flex row, gap-1",
                "items": "{{cluster.evidence_gaps}}",
                "render": {
                    "type": "icon_badge",
                    "icon": "dynamic",  # Icon depends on gap type
                    "gap_icons": {
                        "NULL_RESULT_UNDERREPRESENTED": "📊",
                        "MECHANISM_ABSENT": "🔍",
                        "HIGH_QUALITY_STUDY_ABSENT": "🎓",
                        "CONTRADICTING_EVIDENCE_ABSENT": "⚠️",
                        "SUBGROUP_EVIDENCE_ABSENT": "👥"
                    },
                    "size": "20px",
                    "bg": "#fef3c7",  # Amber background
                    "on_hover": "{{gap_type}}: {{severity}} — Suggested query: {{suggestion_query}}",
                    "on_click": "Copy suggestion to retrieval module"
                }
            },
            
            "contradiction_badge": {
                "condition": "cluster.contradictions.count > 0",
                "background": "#fee2e2",  # Very light red
                "border": "1px solid #fca5a5",  # Light red border
                "text": "⚔️ {{contradiction_count}} conflict",
                "text_color": "#991b1b",  # Dark red
                "on_click": "Open contradiction map view"
            },
            
            "replication_checkmark": {
                "condition": "cluster.replications.count > 0",
                "icon": "✓",
                "color": "#059669",  # Green
                "text": "{{replication_count}} replicates",
                "text_color": "#047857",
                "on_hover": "{{high_confidence_reps}} high-confidence replications"
            }
        },
        
        "row_actions": [
            {
                "label": "Expand",
                "icon": "chevron-down",
                "action": "expand_cluster_view"
            },
            {
                "label": "Gap Details",
                "icon": "info",
                "action": "show_gap_details_modal"
            },
            {
                "label": "Retrieve More",
                "icon": "search",
                "action": "copy_gap_suggestions_to_retrieval"
            }
        ]
    },
    
    
    "EXPANDED_CLUSTER_VIEW": {
        
        "layout": "vertical accordion expansion",
        "default_visible": False,
        "trigger": "Click 'Expand' or click row",
        
        "sections": {
            
            "claim_list": {
                "title": "Claims in Cluster",
                "grouping": "By direction",
                "groups": [
                    {
                        "name": "Supporting ({{count}})",
                        "direction": ["positive", "negative"],
                        "sort_by": "composite_confidence desc",
                        "collapsed_by_default": False
                    },
                    {
                        "name": "Contradicting ({{count}})",
                        "direction": "any_with_contradicting_edges",
                        "collapsed_by_default": False
                    },
                    {
                        "name": "Null Results ({{count}})",
                        "direction": "null",
                        "collapsed_by_default": True
                    }
                ],
                
                "claim_row_layout": {
                    
                    "statement": {
                        "text": "{{truncate(claim.statement_raw, 120)}}",
                        "font_size": "13px",
                        "max_lines": 2,
                        "on_hover": "Show full statement",
                        "on_click": "Open claim detail modal"
                    },
                    
                    "source": {
                        "paper_title": "{{paper.title}}",
                        "year": "({{paper.year}})",
                        "text_color": "#6b7280",
                        "font_size": "12px"
                    },
                    
                    "study_design": {
                        "type": "badge",
                        "text": "{{claim.study_design_type}}",
                        "bg_color": "dynamic",
                        "design_colors": {
                            "RCT": "#dbeafe",
                            "Meta-analysis": "#c7d2fe",
                            "Observational": "#fbbf24",
                            "Animal model": "#fed7aa",
                            "In vitro": "#fbcfe8"
                        }
                    },
                    
                    "direction_arrow": {
                        "positive": "↑ Green",
                        "negative": "↓ Green",
                        "null": "∅ Gray",
                        "icon_size": "18px"
                    },
                    
                    "uncertainty_dots": {
                        "layout": "flex row, gap-1",
                        "items": [
                            {
                                "label": "E",
                                "title": "Extraction Uncertainty",
                                "value": "{{claim.extraction_uncertainty}}",
                                "size": "14px",
                                "fill_percentage": "{{value * 100}}"
                            },
                            {
                                "label": "S",
                                "title": "Study Uncertainty",
                                "value": "{{claim.study_uncertainty}}",
                                "size": "14px",
                                "fill_percentage": "{{value * 100}}"
                            },
                            {
                                "label": "G",
                                "title": "Generalizability Uncertainty",
                                "value": "{{claim.generalizability_uncertainty}}",
                                "size": "14px",
                                "fill_percentage": "{{value * 100}}"
                            },
                            {
                                "label": "R",
                                "title": "Replication Uncertainty",
                                "value": "{{claim.replication_uncertainty}}",
                                "size": "14px",
                                "fill_percentage": "{{value * 100}}"
                            }
                        ],
                        "dot_appearance": {
                            "type": "circle",
                            "border": "1px solid #d1d5db",
                            "fill_color_rule": "linear gradient from white to theme color",
                            "on_hover": "Show value and meaning",
                            "on_click": "Open uncertainty interpretation"
                        }
                    }
                }
            },
            
            "contradiction_map": {
                "title": "Contradictions in This Cluster",
                "visible_if": "cluster.contradictions.count > 0",
                "layout": "grid of pairs",
                
                "contradiction_pair": {
                    "layout": "left | center | right",
                    
                    "left_claim": {
                        "width": "40%",
                        "border": "1px solid #fee2e2",
                        "padding": "8px",
                        "bg": "#fef2f2",
                        "content": {
                            "title": "{{claim_a.statement_raw}}",
                            "paper": "{{paper_a.title}} ({{paper_a.year}})",
                            "study_design": "{{claim_a.study_design}}",
                            "confidence": "{{claim_a.composite_confidence}}"
                        }
                    },
                    
                    "center_badge": {
                        "width": "20%",
                        "text_align": "center",
                        "content": "{{contradiction_severity}}"
                    },
                    
                    "right_claim": {
                        "width": "40%",
                        "border": "1px solid #fee2e2",
                        "padding": "8px",
                        "bg": "#fef2f2",
                        "content": {
                            "title": "{{claim_b.statement_raw}}",
                            "paper": "{{paper_b.title}} ({{paper_b.year}})",
                            "study_design": "{{claim_b.study_design}}",
                            "confidence": "{{claim_b.composite_confidence}}"
                        }
                    }
                }
            },
            
            "gap_details": {
                "title": "Detected Evidence Gaps",
                "visible_if": "cluster.evidence_gaps.length > 0",
                "layout": "list of cards",
                
                "gap_card": {
                    "border": "1px solid #fbbf24",
                    "bg": "#fffbeb",
                    "content": {
                        "gap_type": "{{gap_type}} [{{severity}}]",
                        "description": "{{gap_description}}",
                        "current_evidence": "{{cluster.claim_count}} total, {{null_count}} null, {{mechanistic_count}} mechanistic",
                        "suggested_queries": [
                            "{{suggestion_query_1}}",
                            "{{suggestion_query_2}}"
                        ],
                        "action_button": {
                            "label": "Search for papers",
                            "action": "copy_suggestions_to_retrieval_module",
                            "icon": "search"
                        }
                    }
                }
            }
        }
    },
    
    
    "SECONDARY_VIEW_1_CONTRADICTION_MAP": {
        
        "access": "Toggle from primary view or right-click cluster",
        "layout": "full-page side-by-side pairs",
        
        "purpose": """
        Show only claims involved in contradictions.
        Help operators understand where evidence conflicts.
        """,
        
        "pair_layout": {
            
            "left_column": "CLAIM A",
            "center_column": "SEVERITY & DELTA",
            "right_column": "CLAIM B",
            
            "severity_badges": {
                "HIGH": {"color": "#dc2626", "meaning": "Confidence delta > 0.40"},
                "MEDIUM": {"color": "#f97316", "meaning": "Confidence delta 0.20-0.40"},
                "LOW": {"color": "#eab308", "meaning": "Confidence delta < 0.20"}
            },
            
            "sort_options": ["by_severity", "by_recency", "by_evidence_quality"],
            "current_sort": "by_severity"
        }
    },
    
    
    "SECONDARY_VIEW_2_ENTITY_MAP": {
        
        "access": "Toggle from primary view",
        "layout": "graph visualization or tabular list",
        
        "purpose": "Show entity nodes and their status in glossary",
        
        "node_display": {
            "entity_node": {
                "canonical_form": "{{entity.canonical_form}}",
                "status_badge": {
                    "confirmed": {"bg": "#dcfce7", "color": "#166534"},
                    "provisional": {"bg": "#fef3c7", "color": "#92400e"},
                    "merge_candidate": {"bg": "#fed7aa", "color": "#92400e"},
                    "rejected": {"bg": "#fee2e2", "color": "#991b1b"}
                },
                "surface_forms": "{{entity.surface_forms.join(', ')}}",
                "paper_count": "{{entity.paper_ids.length}}",
                "glossary_version": "v{{entity.glossary_version}}"
            }
        }
    },
    
    
    "UNCERTAINTY_INTERPRETATION_MODAL": {
        
        "trigger": "Click uncertainty dots or 'Uncertainty' button",
        
        "layout": "4-column grid of components",
        
        "component_details": [
            {
                "name": "Extraction Uncertainty",
                "value": "{{extraction_uncertainty}}",
                "visual": "large progress circle",
                "color_scale": "red (0) → yellow (0.5) → green (1)",
                "meaning": "{{extraction_interpretation}}",
                "sources": [
                    "Pass 1 extraction certainty",
                    "Grounding validation (evidence_span check)",
                    "Verification confidence from NLI/LLM",
                    "Internal coherence adjustments"
                ],
                "improvement_suggestions": [
                    "Re-extraction with improved prompt",
                    "Better evidence span selection",
                    "Additional verification tier"
                ]
            },
            {
                "name": "Study Uncertainty",
                "value": "{{study_uncertainty}}",
                "visual": "large progress circle",
                "meaning": "{{study_interpretation}}",
                "sources": [
                    "Study design score",
                    "Hedging language penalties",
                    "Design-claim consistency",
                    "Causal downgrade if applicable"
                ],
                "improvement_suggestions": [
                    "Find higher-quality studies (RCT, meta-analysis)",
                    "Note design limitations in synthesis"
                ]
            },
            {
                "name": "Generalizability Uncertainty",
                "value": "{{generalizability_uncertainty}}",
                "visual": "large progress circle",
                "meaning": "{{generalizability_interpretation}}",
                "sources": [
                    "Population specificity",
                    "Internal conflicts in paper",
                    "Population-specific subgroup flags",
                    "Study type (animal model, in vitro)"
                ],
                "improvement_suggestions": [
                    "Find studies in different populations",
                    "Resolve internal conflicts",
                    "Look for mechanistic support"
                ]
            },
            {
                "name": "Replication Uncertainty",
                "value": "{{replication_uncertainty}}",
                "visual": "large progress circle",
                "meaning": "{{replication_interpretation}}",
                "sources": [
                    "Number of replicating claims",
                    "Number of contradicting claims",
                    "Isolation in evidence graph",
                    "Default 0.50 for new claims"
                ],
                "improvement_suggestions": [
                    "Search for confirming studies",
                    "Investigate contradictions",
                    "Run additional papers through pipeline"
                ]
            }
        ],
        
        "footer": {
            "composite_indicator": "Composite = √(E × S × G × R)",
            "interpretation": "{{composite_interpretation}}",
            "action_buttons": [
                {"label": "Find supporting evidence", "action": "gap_detection_search"},
                {"label": "Export claim details", "action": "export_provenance"}
            ]
        }
    }
}


# UI IMPLEMENTATION NOTES

IMPLEMENTATION_NOTES = """
## Frontend Technology Stack (Recommended)

### Framework
- React 18 with TypeScript
- TailwindCSS for styling
- Recharts or D3.js for visualizations

### Data Visualization Libraries
- react-circular-progressbar (for uncertainty dots)
- recharts (for stacked bars, pie charts)
- reactflow (for entity graph visualization)

### State Management
- React Query (for caching cluster data)
- Zustand (for UI state)

### Components to Build
1. ClusterRow — single cluster display
2. DirectionBar — stacked horizontal bar
3. UncertaintyDots — 4-dot uncertainty visualization
4. ContradictionMap — pair layout
5. EntityGraph — entity node visualization
6. ClaimsExplorerCard — main container

## Data Flow

### Initial Load
GET /api/missions/{mission_id}/clusters
→ Returns: List[cluster] with all fields

### Real-time Updates
WebSocket /ws/missions/{mission_id}
→ Events: cluster_confidence_updated, gap_detected, contradiction_detected

### Filtering
POST /api/missions/{mission_id}/clusters/filter
Body: {min_confidence, hide_isolated, show_gaps_only, quality_filter}

## Performance Considerations

### Pagination
- Show 20 clusters per page by default
- Lazy-load detailed views
- Cache cluster data for 5 minutes

### Virtualization
- Use react-window for large claim lists
- Virtualize contradiction pairs (can be 100+)

### Debouncing
- Filter input: 300ms debounce
- Sort changes: immediate
- Expansion state: immediate

## Accessibility
- ARIA labels on all interactive elements
- Keyboard navigation: Tab, Arrow keys, Enter
- Color not sole indicator (use icons/badges backup)
- Screen reader descriptions for badges
"""

if __name__ == "__main__":
    print(json.dumps(CLAIMS_EXPLORER_SPECIFICATION, indent=2))
    print("\n\n" + IMPLEMENTATION_NOTES)
