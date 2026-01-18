import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import Box from '@mui/material/Box'
import AppBar from '@mui/material/AppBar'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import Container from '@mui/material/Container'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import IconButton from '@mui/material/IconButton'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemText from '@mui/material/ListItemText'
import Skeleton from '@mui/material/Skeleton'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents'
import { fetchLeaderboard } from '../api'

export function LeaderboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['leaderboard'],
    queryFn: fetchLeaderboard,
    staleTime: 5 * 60 * 1000,
  })

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <AppBar position="sticky" elevation={0}>
        <Toolbar>
          <IconButton
            edge="start"
            color="inherit"
            component={Link}
            to="/"
            sx={{ mr: 2 }}
          >
            <ArrowBackIcon />
          </IconButton>
          <Typography variant="h6" component="h1" sx={{ fontWeight: 700 }}>
            Riddle Leaderboard
          </Typography>
        </Toolbar>
      </AppBar>

      <Container component="main" maxWidth="sm" sx={{ flex: 1, py: 2 }}>
        <Card>
          <CardContent>
            {isLoading ? (
              <Box>
                {[1, 2, 3, 4, 5].map((i) => (
                  <Skeleton key={i} variant="rectangular" height={48} sx={{ mb: 1 }} />
                ))}
              </Box>
            ) : !data?.players?.length ? (
              <Typography color="text.secondary" textAlign="center">
                No scores yet. Be the first to solve a riddle!
              </Typography>
            ) : (
              <>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Season: {data.season_start || 'Current'}
                </Typography>
                <List disablePadding>
                  {data.players.map((player, index) => (
                    <ListItem
                      key={player.display_name}
                      sx={{
                        bgcolor: index === 0 ? 'action.selected' : 'transparent',
                        borderRadius: 1,
                        mb: 0.5,
                      }}
                    >
                      <Box
                        sx={{
                          width: 32,
                          height: 32,
                          borderRadius: '50%',
                          bgcolor: index === 0 ? 'warning.main' : index === 1 ? 'grey.400' : index === 2 ? 'warning.dark' : 'grey.700',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          mr: 2,
                          color: 'white',
                          fontWeight: 700,
                        }}
                      >
                        {index === 0 ? <EmojiEventsIcon fontSize="small" /> : index + 1}
                      </Box>
                      <ListItemText
                        primary={player.display_name}
                        secondary={`${player.points} pts • ${player.wins} wins`}
                      />
                    </ListItem>
                  ))}
                </List>
              </>
            )}
          </CardContent>
        </Card>

        {/* Scoring Explanation */}
        <Card sx={{ mt: 2 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
              How Scoring Works
            </Typography>
            <List dense disablePadding>
              <ListItem sx={{ py: 0.5 }}>
                <ListItemText
                  primary="🥇 First to Solve"
                  secondary="3 points + credited as the day's winner"
                  primaryTypographyProps={{ fontWeight: 500 }}
                />
              </ListItem>
              <ListItem sx={{ py: 0.5 }}>
                <ListItemText
                  primary="✅ Correct Answer"
                  secondary="2 points (after first solver)"
                  primaryTypographyProps={{ fontWeight: 500 }}
                />
              </ListItem>
              <ListItem sx={{ py: 0.5 }}>
                <ListItemText
                  primary="❌ Wrong Guess"
                  secondary="0 points (but keep trying!)"
                  primaryTypographyProps={{ fontWeight: 500 }}
                />
              </ListItem>
              <ListItem sx={{ py: 0.5 }}>
                <ListItemText
                  primary="🔄 Already Solved"
                  secondary="Once you solve a riddle, you can't earn more points on it"
                  primaryTypographyProps={{ fontWeight: 500 }}
                />
              </ListItem>
            </List>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              A new riddle appears each morning at 7 AM in the daily email.
              Submit guesses via email reply or the website. The AI judges
              whether your answer is correct (synonyms and close matches count!).
            </Typography>
          </CardContent>
        </Card>
      </Container>
    </Box>
  )
}
