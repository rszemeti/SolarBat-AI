#!/bin/bash
# Update test expectations for new backwards simulation strategies

echo "Updating test scenario expectations..."

# Update cloudy_summer_day.json
cat > test_scenarios/scenarios/typical/cloudy_summer_day_expectations.tmp << 'EOF'
  "expected_outcomes": {
    "feed_in_priority_hours": ">10",
    "total_cost_max": 3.5,
    "notes": "High solar surplus requires Feed-in Priority to prevent clipping"
  }
}
EOF

# Update winter_sunny_day.json
cat > test_scenarios/scenarios/typical/winter_sunny_day_expectations.tmp << 'EOF'
  "expected_outcomes": {
    "feed_in_priority_hours": ">6",
    "discharge_during_peak": true,
    "notes": "Winter solar surplus requires Feed-in Priority; should also discharge during expensive evening peak"
  }
}
EOF

# Apply changes to cloudy_summer_day.json
sed -i.bak '/"expected_outcomes": {/,/^}/c\
  "expected_outcomes": {\
    "feed_in_priority_hours": ">10",\
    "total_cost_max": 3.5,\
    "notes": "High solar surplus requires Feed-in Priority to prevent clipping"\
  }\
}' test_scenarios/scenarios/typical/cloudy_summer_day.json

# Apply changes to winter_sunny_day.json  
sed -i.bak '/"expected_outcomes": {/,/^}/c\
  "expected_outcomes": {\
    "feed_in_priority_hours": ">6",\
    "discharge_during_peak": true,\
    "notes": "Winter solar surplus requires Feed-in Priority; should also discharge during expensive evening peak"\
  }\
}' test_scenarios/scenarios/typical/winter_sunny_day.json

# Clean up
rm -f test_scenarios/scenarios/typical/*_expectations.tmp
rm -f test_scenarios/scenarios/typical/*.bak

echo "✅ Test expectations updated!"
echo ""
echo "Changes:"
echo "  - cloudy_summer_day: feed_in_priority_hours changed from 0 to '>10'"
echo "  - winter_sunny_day: feed_in_priority_hours changed from 0 to '>6'"
