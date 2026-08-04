def add_weekly_results(email, week_num, correct_picks, incorrect_picks, is_winner, total_wins):
    """
    Add new weekly results to the FBP-Results-2025 table
    """
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('FBP-Results-2025')
    
    try:
        response = table.put_item(
            Item={
                'email': email,
                'week': Decimal(str(week_num)),
                'correctpicks': Decimal(str(correct_picks)),
                'incorrectpicks': Decimal(str(incorrect_picks)),
                'winner': is_winner,
                'totalwins': Decimal(str(total_wins))
            }
        )
        print(f"Successfully added results for {email}, Week {week_num}")
        return True
        
    except Exception as e:
        print(f"Error adding results: {str(e)}")
        return False

# Example usage:
add_weekly_results('user@example.com', 16, 12, 4, True, 3)
