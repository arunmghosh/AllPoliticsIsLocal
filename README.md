# All Politics Is Local
An interactive election simulation game in which you run for office and progress to higher positions as you win and gain more experience. You have a fifty year career timeline in which to reach the presidency. Lose an election, and you lose the game. You also have the option to simulate prior election data to get an idea of how districts vote and select where / with what party you want to run. 

## 1. Full Problem Specification
### Simulated Country
For simplicity, this simulation enforces a strict hierarchy among levels of office: 
1. Nation
2. State
3. City
4. District

The nation contains 51 states, each state contains 11 cities, each city contains 35 districts, and each district has 10,001 people. I had to choose odd numbers to eliminate the possibility of ties in elections. 

There are also three different levels of government:
1. Federal (President, Senate, House of Representatives)
2. State (Governor, State Legislature)
3. Local (Mayor, City Council)

The entire nation votes for the President, each state elects a Governor and 3 Senators, each city elects a Mayor and 1 member of the House of Representatives, and each district elects a member of the State Legislature and a member of the City Council. 

Here is the scope and term length for each position:
- President: Elected by entire nation, 8 year term
- Governors & Senators: Elected by a state, 6 year term
- Mayors & House Members: Elected by a city, 4 year term
- State Legislators & City Council Members: Elected by a district, 2 year term

A president can only serve one term, but there no term limits imposed on other positions. 

### Simulated Politics
Politics is represented by a set of issues, with each have an ideology spectrum represented by the interval (0,1). Low numbers mean a conservative position on the issue, while high numbers mean a liberal position. You have the option to choose up to 3 issues to use for the simulation. 

These issues are debated by parties. Each party has a platform, which is a vector of positions taken on issues. The positions can either be 0.25 (mean of conservative values) or 0.75 (mean of liberal values). Each party must have a unique platform, so if there are I issues, there can be at most 2^I parties. You will have the option to choose how many parties you want, within the range of 2 and 2^I. 

All parties nominate a candidate to run for every position. Candidates each have their own platform, sampled from a random distribution with the rule that they must be liberal or conservative on the same issues that their party is. The conservative range is (0,0.5), and the liberal range is (0.5,1). 

Candidates are elected by people, who each belong to the nation, a state, a city and a district. Instead of each person having their own position vector, each district uses its own position vector to split 10,001 votes among the candidates. Districts are assigned position vectors according the following algorithm:
1. Every state is given a random position vector with each position drawn randomly from (0,1)
2. Every city within each state is given a random position vector with each position drawn randomly from a triangular distribution with endpoints at 0 and 1, and the peak (highest probability) at the position of the state
3. Every district with each city is given a random position vector with each position drawn randomly from a triangular distribution with endpoints at 0 and 1, and the peak at the position of the city

The reason this project is called "All Politics Is Local" is because only the district position vectors actually matter for voting. All higher level results are just sums of district results. 

### Simulated Voting
